"""
Append-only hash-linked ledger for photo certificate events.
Each entry records its own hash and the hash of the previous entry,
forming a tamper-evident chain within the SQLite database.

NOTE: This is NOT a blockchain. It is a local hash-linked audit log.
"""
from __future__ import annotations

import hashlib
import json
import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import LedgerEntry


def _compute_record_hash(
    entry_id: int,
    certificate_id: int,
    event_type: str,
    event_data: Optional[str],
    timestamp: datetime.datetime,
    prev_hash: Optional[str],
) -> str:
    payload = json.dumps(
        {
            "entry_id": entry_id,
            "certificate_id": certificate_id,
            "event_type": event_type,
            "event_data": event_data,
            "timestamp": timestamp.isoformat(),
            "prev_hash": prev_hash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def append_ledger_entry(
    db: Session,
    certificate_id: int,
    event_type: str,
    event_data: Optional[dict] = None,
) -> LedgerEntry:
    """Append a new entry to the ledger and commit."""
    # Get the last entry for its hash
    last = (
        db.query(LedgerEntry)
        .order_by(LedgerEntry.id.desc())
        .first()
    )
    prev_hash = last.record_hash if last else None
    event_data_str = json.dumps(event_data) if event_data else None
    now = datetime.datetime.utcnow()

    # We need the final ID to compute the hash, so flush first
    entry = LedgerEntry(
        certificate_id=certificate_id,
        event_type=event_type,
        event_data=event_data_str,
        record_hash="PENDING",
        prev_record_hash=prev_hash,
        timestamp=now,
    )
    db.add(entry)
    db.flush()  # assigns entry.id without committing

    record_hash = _compute_record_hash(
        entry.id, certificate_id, event_type, event_data_str, now, prev_hash
    )
    entry.record_hash = record_hash
    db.commit()
    db.refresh(entry)
    return entry


def verify_ledger_integrity(db: Session) -> dict:
    """Verify the full chain integrity. Returns a status dict."""
    entries = db.query(LedgerEntry).order_by(LedgerEntry.id.asc()).all()
    if not entries:
        return {
            "total_entries": 0,
            "is_intact": True,
            "first_entry_time": None,
            "last_entry_time": None,
            "broken_at_entry": None,
            "message": "Ledger is empty.",
        }

    prev_hash: Optional[str] = None
    for entry in entries:
        expected = _compute_record_hash(
            entry.id,
            entry.certificate_id,
            entry.event_type,
            entry.event_data,
            entry.timestamp,
            prev_hash,
        )
        if entry.record_hash != expected:
            return {
                "total_entries": len(entries),
                "is_intact": False,
                "first_entry_time": entries[0].timestamp,
                "last_entry_time": entries[-1].timestamp,
                "broken_at_entry": entry.id,
                "message": f"Ledger chain broken at entry {entry.id}.",
            }
        prev_hash = entry.record_hash

    return {
        "total_entries": len(entries),
        "is_intact": True,
        "first_entry_time": entries[0].timestamp,
        "last_entry_time": entries[-1].timestamp,
        "broken_at_entry": None,
        "message": "Ledger chain is intact.",
    }
