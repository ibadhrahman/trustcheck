"""
Duplicate payment detection.

Uses:
  1. SHA-256 exact file-hash match
  2. Perceptual-hash similarity
  3. Transaction ID / UTR / reference HMAC fingerprint match

Does NOT classify duplicates as fraud — provides evidence for seller review.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import PaymentReference, PaymentSubmission

logger = logging.getLogger(__name__)


def _hmac_fingerprint(value: str) -> str:
    """Compute HMAC-SHA256 fingerprint of a normalized transaction reference."""
    normalized = value.strip().upper().replace(" ", "")
    return hmac.new(
        settings.hmac_secret.encode(),
        normalized.encode(),
        hashlib.sha256,
    ).hexdigest()


def record_payment_reference(
    db: Session,
    seller_id: int,
    order_id: int,
    submission_id: int,
    tx_ref: Optional[str],
) -> Optional[str]:
    """
    Record a HMAC fingerprint of the transaction reference.
    Returns the fingerprint if stored, None if no reference given.
    """
    if not tx_ref:
        return None

    fingerprint = _hmac_fingerprint(tx_ref)

    ref = PaymentReference(
        seller_id=seller_id,
        order_id=order_id,
        submission_id=submission_id,
        tx_ref_hmac=fingerprint,
    )
    db.add(ref)
    # Caller is responsible for commit
    return fingerprint


def check_duplicate_reference(
    db: Session,
    tx_ref: str,
    exclude_submission_id: Optional[int] = None,
) -> Optional[dict]:
    """
    Check whether a transaction reference fingerprint already exists.
    Returns details dict if duplicate found, else None.
    """
    fingerprint = _hmac_fingerprint(tx_ref)

    query = db.query(PaymentReference).filter(
        PaymentReference.tx_ref_hmac == fingerprint
    )

    # Check within the configured time window
    if settings.duplicate_window_hours > 0:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            hours=settings.duplicate_window_hours
        )
        query = query.filter(PaymentReference.first_seen_at >= cutoff)

    if exclude_submission_id is not None:
        query = query.filter(
            PaymentReference.submission_id != exclude_submission_id
        )

    existing = query.first()
    if existing:
        return {
            "duplicate_found": True,
            "first_seen_submission_id": existing.submission_id,
            "first_seen_order_id": existing.order_id,
            "first_seen_at": existing.first_seen_at.isoformat(),
            "message": (
                "This transaction reference has been seen in a previous submission. "
                "This is a strong indicator of a reused payment proof. "
                "Review independently before dispatching."
            ),
        }
    return None


def check_duplicate_screenshot(
    db: Session,
    sha256: Optional[str] = None,
    phash: Optional[str] = None,
    exclude_submission_id: Optional[int] = None,
) -> Optional[dict]:
    """
    Check for visually or byte-identical screenshots.
    Returns details if a duplicate is found.
    """
    from app.analysis.forensics import phash_distance

    if sha256:
        query = db.query(PaymentSubmission).filter(
            PaymentSubmission.screenshot_sha256 == sha256
        )
        if exclude_submission_id:
            query = query.filter(PaymentSubmission.id != exclude_submission_id)
        match = query.first()
        if match:
            return {
                "duplicate_found": True,
                "match_type": "exact_file",
                "matched_submission_id": match.id,
                "message": (
                    "This exact screenshot file has been submitted before "
                    "(SHA-256 hash matches). Treat as a strong duplicate warning."
                ),
            }

    if phash:
        # Check perceptual similarity against recent submissions
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            hours=settings.duplicate_window_hours
        )
        recent = (
            db.query(PaymentSubmission)
            .filter(
                PaymentSubmission.screenshot_phash != None,
                PaymentSubmission.created_at >= cutoff,
            )
            .all()
        )
        for sub in recent:
            if exclude_submission_id and sub.id == exclude_submission_id:
                continue
            if not sub.screenshot_phash:
                continue
            dist = phash_distance(phash, sub.screenshot_phash)
            if dist is not None and dist <= settings.phash_similarity_threshold:
                return {
                    "duplicate_found": True,
                    "match_type": "perceptual_similar",
                    "matched_submission_id": sub.id,
                    "phash_distance": dist,
                    "message": (
                        f"This screenshot is visually very similar to a previous submission "
                        f"(perceptual hash distance: {dist}). "
                        "This may indicate a reused or lightly modified screenshot."
                    ),
                }

    return None
