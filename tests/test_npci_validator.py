"""
tests/test_npci_validator.py

Test suite for the NPCI Julian-Cycle UTR Checksum Validator innovation module.
"""
from datetime import date
from app.analysis.npci_validator import validate_utr_npci


def test_valid_utr_today():
    """A UTR whose year digit and Julian day match today's date should pass."""
    today = date(2026, 10, 10)
    # 2026 Julian day for Oct 10 is 283 (Jan 31 + Feb 28 + Mar 31 + Apr 30 + May 31 + Jun 30 + Jul 31 + Aug 31 + Sep 30 + Oct 10)
    utr = "628312345678"
    res = validate_utr_npci(utr, claimed_date=today)
    assert res.is_valid_format is True
    assert res.verdict == "valid"
    assert res.decoded_year_digit == 6
    assert res.decoded_julian_day == 283
    assert res.julian_day_valid is True
    assert res.year_match is True
    assert res.decoded_date == "2026-10-10"


def test_impossible_julian_day():
    """A UTR with Julian day > 366 (e.g. 892) is mathematically impossible on any Indian bank rail."""
    utr = "689212345678"
    res = validate_utr_npci(utr, claimed_date=date(2026, 10, 10))
    assert res.is_valid_format is True
    assert res.julian_day_valid is False
    assert res.verdict == "impossible_julian_day"
    assert "exceeds calendar limits" in (res.detail or "")


def test_year_mismatch():
    """A UTR with year digit 3 (2023) submitted for a 2026 order should be flagged as recycled/mismatched."""
    utr = "320145678912"
    res = validate_utr_npci(utr, claimed_date=date(2026, 10, 10))
    assert res.is_valid_format is True
    assert res.verdict == "year_mismatch"
    assert res.year_match is False
    assert res.decoded_year_digit == 3


def test_future_utr():
    """A UTR encoding a date in the future relative to claimed payment date should be flagged."""
    # Julian day 350 in 2026 is mid-December 2026
    utr = "635012345678"
    res = validate_utr_npci(utr, claimed_date=date(2026, 10, 10))
    assert res.is_valid_format is True
    assert res.verdict == "future_utr"


def test_stale_recycled_utr():
    """A UTR encoding a date months ago relative to claimed date should be flagged as stale."""
    # Julian day 015 in 2026 is Jan 15 2026
    utr = "601512345678"
    res = validate_utr_npci(utr, claimed_date=date(2026, 10, 10), max_staleness_days=7)
    assert res.is_valid_format is True
    assert res.verdict == "stale_utr"
    assert res.freshness_ok is False


def test_format_invalid_alphanumeric():
    """Input with fewer than 12 digits should be flagged as format_invalid."""
    res = validate_utr_npci("NOT-A-UTR")
    assert res.is_valid_format is False
    assert res.verdict == "format_invalid"
