"""Private helpers for buyer access codes, outcome evidence, and seller warnings."""
from __future__ import annotations

import hashlib
import hmac
import io
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Order, OrderOutcome
from app.referral_codes import generate_verification_tx_id

_MIME_FORMATS = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}


def new_buyer_access_code() -> str:
    """Generate a clean, unambiguous human-readable reference code like TXN-PCFY-4A5K."""
    return generate_verification_tx_id()


def buyer_access_fingerprint(code: str) -> str:
    cleaned = code.strip()
    if cleaned.upper().startswith("TXN-"):
        cleaned = cleaned.upper()
    return hmac.new(
        settings.hmac_secret.encode("utf-8"),
        ("buyer-order-access:" + cleaned).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def save_private_evidence(file: Optional[UploadFile]) -> Optional[tuple[str, str, int]]:
    """Validate and normalize an image, strip metadata, and save outside static files."""
    if file is None or not file.filename:
        return None
    if file.content_type not in _MIME_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Evidence must be a JPEG, PNG, or WebP image.",
        )

    raw = file.file.read(settings.max_upload_size_bytes + 1)
    if len(raw) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Photo exceeds {settings.max_upload_size_mb} MB limit.",
        )

    expected_format, extension = _MIME_FORMATS[file.content_type]
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            if probe.format != expected_format:
                raise HTTPException(status_code=415, detail="Photo content does not match its file type.")
            if probe.width * probe.height > 20_000_000:
                raise HTTPException(status_code=413, detail="Photo dimensions are too large.")
            probe.verify()
        with Image.open(io.BytesIO(raw)) as opened:
            image = ImageOps.exif_transpose(opened)
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            if expected_format == "JPEG":
                image = image.convert("RGB")
            elif expected_format == "PNG" and has_alpha:
                image = image.convert("RGBA")
            elif expected_format == "PNG":
                image = image.convert("RGB")
            elif has_alpha:
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")
            cleaned = io.BytesIO()
            save_options: dict[str, Any] = {"format": expected_format}
            if expected_format == "JPEG":
                save_options.update({"quality": 90, "optimize": True})
            elif expected_format == "WEBP":
                save_options.update({"quality": 88, "method": 4})
            else:
                save_options.update({"optimize": True})
            # Saving a newly constructed image without `exif` strips location/device metadata.
            image.save(cleaned, **save_options)
            data = cleaned.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid supported image.")

    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Processed photo exceeds {settings.max_upload_size_mb} MB limit.",
        )

    storage_key = secrets.token_hex(24) + extension
    private_root = Path(settings.private_upload_dir).resolve()
    private_root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        private_root.chmod(0o700)
    path = (private_root / storage_key).resolve()
    if path.parent != private_root:
        raise HTTPException(status_code=500, detail="Private evidence storage is unavailable.")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(path)
    return storage_key, file.content_type, len(data)


def load_private_evidence(storage_key: str) -> bytes:
    root = Path(settings.private_upload_dir).resolve()
    path = (root / storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence photo not found.")
    return path.read_bytes()


def delete_private_evidence(storage_key: str) -> None:
    root = Path(settings.private_upload_dir).resolve()
    path = (root / storage_key).resolve()
    if path.parent == root and path.is_file():
        path.unlink()


def seller_has_warning(db: Session, seller_id: int, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    window_start = now - timedelta(days=settings.order_issue_warning_window_days)
    rows = (
        db.query(OrderOutcome.order_id)
        .join(Order, Order.id == OrderOutcome.order_id)
        .filter(
            Order.seller_id == seller_id,
            OrderOutcome.outcome == "problem",
            OrderOutcome.status.in_(("awaiting_seller", "resolution_offered")),
            OrderOutcome.response_deadline <= now,
            OrderOutcome.reported_at >= window_start,
        )
        .all()
    )
    # Without buyer accounts, TrustCheck can verify unique orders but cannot reliably
    # prove that reports across different orders came from distinct people.
    distinct_orders = {order_id for (order_id,) in rows}
    return len(distinct_orders) >= settings.order_issue_warning_threshold
