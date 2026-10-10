"""
app/analysis/npci_validator.py

NPCI Julian-Cycle UTR Checksum Validator — TrustCheck Innovation Module.

Indian UPI 12-digit UTR (Unique Transaction Reference) numbers follow NPCI
settlement rail format specifications. This module decodes and validates
the embedded temporal metadata to catch:

  1. Synthetic / randomly generated UTRs from fake payment generator APKs
  2. Recycled / stale UTRs resubmitted from old transactions
  3. Mathematically impossible Julian day codes (> 366)

UTR Structure (12-digit numeric):
  ┌─────┬───────────┬──────────────────┐
  │ Y   │ DDD       │ SSSSSSSS         │
  │ (1) │ (3 digits)│ (8 digits)       │
  └─────┴───────────┴──────────────────┘
  Y    = Last digit of the calendar year (e.g. '6' for 2026)
  DDD  = Julian day of the year (001–365, or 366 for leap years)
  SSSS = Bank switch sequence / settlement batch number

Note: Some banks use slightly different formats (e.g. leading bank code).
This validator checks the most common NPCI UPI format and flags anomalies
without hard-rejecting edge cases from non-standard bank gateways.
"""
from __future__ import annotations

import calendar
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

class NPCIValidationResult:
    """Structured result from NPCI Julian-Cycle UTR validation."""

    is_valid_format: Optional[bool]
    decoded_year_digit: Optional[int]
    decoded_julian_day: Optional[int]
    decoded_date: Optional[date]
    claimed_date: Optional[date]
    year_match: Optional[bool]
    julian_day_valid: Optional[bool]
    date_delta_days: Optional[int]
    freshness_ok: Optional[bool]
    verdict: Optional[str]
    detail: Optional[str]
    confidence: Optional[float]

    __slots__ = (
        "is_valid_format",
        "decoded_year_digit",
        "decoded_julian_day",
        "decoded_date",
        "claimed_date",
        "year_match",
        "julian_day_valid",
        "date_delta_days",
        "freshness_ok",
        "verdict",
        "detail",
        "confidence",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> dict:
        return {slot: getattr(self, slot) for slot in self.__slots__}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_leap_year(year: int) -> bool:
    """Check if a given year is a leap year."""
    return calendar.isleap(year)


def _julian_day_of_date(d: date) -> int:
    """Return the Julian day-of-year (1-based) for a given date."""
    return d.timetuple().tm_yday


def _date_from_julian(year: int, julian_day: int) -> Optional[date]:
    """Reconstruct a calendar date from year + Julian day."""
    try:
        return date(year, 1, 1) + timedelta(days=julian_day - 1)
    except (ValueError, OverflowError):
        return None


def _extract_12_digit_utr(raw: str) -> Optional[str]:
    """
    Extract a contiguous 12-digit numeric string from the raw input.
    Handles common prefixes like 'UPI/', bank codes, spaces, dashes.
    """
    if not raw:
        return None
    # Strip common prefixes
    cleaned = re.sub(r"(?i)^(UPI[/\\]?|UTR[:\s]*|REF[:\s]*)", "", raw.strip())
    # Remove spaces, dashes, dots
    cleaned = re.sub(r"[\s\-.]", "", cleaned)
    # Find the first contiguous 12-digit numeric block
    match = re.search(r"\d{12}", cleaned)
    return match.group(0) if match else None


def _infer_full_year(year_digit: int, reference_date: Optional[date] = None) -> int:
    """
    Infer the full 4-digit year from the single trailing digit.
    Uses the reference date's decade context. E.g. digit '6' in 2026 → 2026.
    """
    ref = reference_date or date.today()
    decade_base = (ref.year // 10) * 10  # e.g. 2020
    candidate = decade_base + year_digit

    # If the candidate is more than 1 year in the future, it's likely previous decade
    if candidate > ref.year + 1:
        candidate -= 10

    return candidate


def parse_claimed_date(val: Any) -> Optional[date]:
    """Parse flexible date inputs (date, datetime, ISO string, natural language strings)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        val = val.strip()
        for fmt in (
            "%Y-%m-%d",
            "%d %b %Y",
            "%d %B %Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b, %Y",
            "%Y/%m/%d",
            "%d.%m.%Y",
        ):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                pass
        m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", val)
        if m:
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2)[:3]} {m.group(3)}", "%d %b %Y").date()
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

def validate_utr_npci(
    utr_raw: str,
    claimed_date: Any = None,
    max_staleness_days: int = 7,
) -> NPCIValidationResult:
    """
    Validate a 12-digit UPI UTR against NPCI Julian-Cycle specifications.

    Parameters
    ----------
    utr_raw : str
        The raw UTR / transaction reference string.
    claimed_date : Any, optional
        The date the buyer claims the payment was made (date, datetime, or str).
        If None, defaults to today.
    max_staleness_days : int
        Maximum allowed age (in days) of a UTR relative to claimed_date.
        Beyond this, the UTR is flagged as stale / recycled.

    Returns
    -------
    NPCIValidationResult
        Structured validation result with verdict and decoded metadata.
    """
    today = date.today()
    claimed = parse_claimed_date(claimed_date) or today

    # Step 1: Extract 12-digit numeric UTR
    utr_12 = _extract_12_digit_utr(utr_raw)

    if not utr_12:
        return NPCIValidationResult(
            is_valid_format=False,
            verdict="format_invalid",
            detail=f"Could not extract a valid 12-digit numeric UTR from '{utr_raw}'.",
            confidence="high",
        )

    # Step 2: Decode Y (year digit) and DDD (Julian day)
    year_digit = int(utr_12[0])
    julian_day = int(utr_12[1:4])

    # Step 3: Validate Julian day range
    inferred_year = _infer_full_year(year_digit, claimed)
    max_days = 366 if _is_leap_year(inferred_year) else 365

    if julian_day < 1 or julian_day > max_days:
        return NPCIValidationResult(
            is_valid_format=True,
            decoded_year_digit=year_digit,
            decoded_julian_day=julian_day,
            decoded_date=None,
            claimed_date=claimed.isoformat() if claimed else None,
            year_match=None,
            julian_day_valid=False,
            date_delta_days=None,
            freshness_ok=False,
            verdict="impossible_julian_day",
            detail=(
                f"Julian day {julian_day:03d} exceeds calendar limits "
                f"(max {max_days} for year {inferred_year}). "
                f"This UTR is mathematically impossible on any Indian banking switch."
            ),
            confidence="definitive",
        )

    # Step 4: Reconstruct the decoded date
    decoded_date = _date_from_julian(inferred_year, julian_day)
    decoded_date_str = decoded_date.isoformat() if decoded_date else None

    # Step 5: Year digit match check
    claimed_year_digit = claimed.year % 10
    year_match = (year_digit == claimed_year_digit)

    # Step 6: Chronometric delta (decoded date vs claimed date)
    if decoded_date:
        delta = (claimed - decoded_date).days
    else:
        delta = None

    # Step 7: Freshness assessment
    freshness_ok = True
    if delta is not None and abs(delta) > max_staleness_days:
        freshness_ok = False

    # Step 8: Build verdict
    verdict, detail = _compute_verdict(
        year_match=year_match,
        julian_day_valid=True,
        freshness_ok=freshness_ok,
        delta=delta,
        decoded_date_str=decoded_date_str,
        claimed_date_str=claimed.isoformat(),
        year_digit=year_digit,
        julian_day=julian_day,
        inferred_year=inferred_year,
    )

    return NPCIValidationResult(
        is_valid_format=True,
        decoded_year_digit=year_digit,
        decoded_julian_day=julian_day,
        decoded_date=decoded_date_str,
        claimed_date=claimed.isoformat(),
        year_match=year_match,
        julian_day_valid=True,
        date_delta_days=delta,
        freshness_ok=freshness_ok,
        verdict=verdict,
        detail=detail,
        confidence=_confidence_level(verdict),
    )


def _compute_verdict(
    *,
    year_match: bool,
    julian_day_valid: bool,
    freshness_ok: bool,
    delta: Optional[int],
    decoded_date_str: Optional[str],
    claimed_date_str: str,
    year_digit: int,
    julian_day: int,
    inferred_year: int,
) -> tuple[str, str]:
    """Determine the final verdict string and human-readable detail."""

    if not year_match:
        return (
            "year_mismatch",
            (
                f"UTR year digit '{year_digit}' (-> {inferred_year}) does not match "
                f"the claimed payment date {claimed_date_str}. "
                f"This suggests the receipt may be recycled from a different year."
            ),
        )

    if delta is not None and delta < -1:
        # Decoded date is in the future relative to claimed date
        return (
            "future_utr",
            (
                f"UTR encodes Julian day {julian_day:03d} (-> {decoded_date_str}), "
                f"which is {abs(delta)} day(s) AFTER the claimed payment date "
                f"{claimed_date_str}. A legitimate UTR cannot reference a future "
                f"settlement date."
            ),
        )

    if not freshness_ok and delta is not None:
        return (
            "stale_utr",
            (
                f"UTR encodes date {decoded_date_str} (Julian day {julian_day:03d}), "
                f"which is {abs(delta)} day(s) away from the claimed payment date "
                f"{claimed_date_str}. This exceeds the freshness threshold and "
                f"suggests a recycled or outdated transaction reference."
            ),
        )

    # All checks passed
    return (
        "valid",
        (
            f"UTR year digit '{year_digit}' and Julian day {julian_day:03d} "
            f"(-> {decoded_date_str}) are consistent with the claimed payment "
            f"date {claimed_date_str}. NPCI rail audit passed."
        ),
    )


def _confidence_level(verdict: str) -> str:
    """Map verdict to a confidence descriptor."""
    return {
        "valid":                "high",
        "year_mismatch":        "high",
        "future_utr":           "definitive",
        "stale_utr":            "medium",
        "impossible_julian_day": "definitive",
        "format_invalid":       "high",
    }.get(verdict, "medium")
