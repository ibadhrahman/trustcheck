"""Temporary analysis stubs for the Backend A / Backend B handoff.

Backend B will replace this file's contents after the Stage 1 stub commit.
Keep these import names stable for the FastAPI routes:

    from app.analysis import (
        analyze_payment_screenshot,
        analyze_image,
        check_scam_text,
        phash,
    )
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


DISCLAIMER = "Risk estimate, not proof. Confirm the credit in your bank app."
STUB_REASON = "Backend B's analysis implementation is not installed; no checks were performed."


def _safe_amount(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        amount = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return amount if math.isfinite(amount) else None


def _safe_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _stub_result(
    reason: str = STUB_REASON,
    *,
    amount: float | None = None,
    upi_id: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Return a cautious placeholder in the shared analysis result shape."""
    return {
        "score": 50,
        "verdict": "careful",
        "reasons": [{"level": "warn", "text": reason}],
        "details": {
            "amount": amount,
            "upi_id": upi_id,
            "txn_id": None,
            "date": date,
            "matches": {"amount": False, "upi_id": False, "date": False},
        },
        "heatmap_png_base64": None,
        "disclaimer": DISCLAIMER,
    }


def analyze_payment_screenshot(image_bytes: bytes, expected: dict) -> dict[str, Any]:
    """Placeholder payment analysis; it deliberately does not verify screenshots."""
    try:
        expected_values = expected if isinstance(expected, Mapping) else {}
        return _stub_result(
            amount=_safe_amount(expected_values.get("amount")),
            upi_id=_safe_text(expected_values.get("upi_id")),
            date=_safe_text(expected_values.get("order_date")),
        )
    except Exception:
        return _stub_result("The payment screenshot could not be checked by the analysis stub.")


def analyze_image(image_bytes: bytes) -> dict[str, Any]:
    """Placeholder image analysis; it deliberately does not inspect the image."""
    try:
        return _stub_result("The image could not be checked because the analysis stub is active.")
    except Exception:
        return _stub_result("The image could not be checked by the analysis stub.")


def check_scam_text(text: str) -> dict[str, Any]:
    """Placeholder scam-text analysis; it deliberately does not inspect the text."""
    try:
        return _stub_result("The text could not be checked because the analysis stub is active.")
    except Exception:
        return _stub_result("The text could not be checked by the analysis stub.")


def phash(image_bytes: bytes) -> str:
    """Return a fixed placeholder hash; Backend B will provide the real pHash."""
    return "STUB-PHASH"


__all__ = [
    "analyze_payment_screenshot",
    "analyze_image",
    "check_scam_text",
    "phash",
]
