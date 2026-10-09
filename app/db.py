"""SQLite connection and schema setup for TrustCheck."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("TRUSTCHECK_DB_PATH", PROJECT_ROOT / "trustcheck.db"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS sellers (
    seller_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    shop_name TEXT NOT NULL,
    upi_id TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS certificates (
    cert_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL,
    title TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    image_path TEXT NOT NULL,
    photo_url TEXT NOT NULL,
    created_at TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    link_hash TEXT NOT NULL UNIQUE,
    FOREIGN KEY (seller_id) REFERENCES sellers (seller_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL,
    photo_id TEXT,
    product_name TEXT NOT NULL,
    price REAL NOT NULL CHECK (price >= 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'proof-submitted', 'paid')),
    link TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    reference_id TEXT,
    FOREIGN KEY (seller_id) REFERENCES sellers (seller_id) ON DELETE CASCADE,
    FOREIGN KEY (photo_id) REFERENCES certificates (cert_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS payment_references (
    reference_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('verified', 'needs-review', 'suspicious', 'confirmed', 'expired')),
    screenshot_sha256 TEXT NOT NULL,
    txn_id TEXT,
    screenshot_path TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders (order_id) ON DELETE CASCADE,
    FOREIGN KEY (seller_id) REFERENCES sellers (seller_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS override_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    action TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    FOREIGN KEY (reference_id) REFERENCES payment_references (reference_id) ON DELETE CASCADE,
    FOREIGN KEY (seller_id) REFERENCES sellers (seller_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_certificates_seller_id
    ON certificates (seller_id);
CREATE INDEX IF NOT EXISTS idx_orders_seller_id
    ON orders (seller_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at
    ON orders (created_at);
CREATE INDEX IF NOT EXISTS idx_payment_references_order_id
    ON payment_references (order_id);
CREATE INDEX IF NOT EXISTS idx_payment_references_seller_id
    ON payment_references (seller_id);
CREATE INDEX IF NOT EXISTS idx_payment_references_screenshot_sha256
    ON payment_references (screenshot_sha256);
CREATE INDEX IF NOT EXISTS idx_payment_references_txn_id
    ON payment_references (txn_id);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a configured connection and always close it after the operation."""
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create the database directory, tables, and indexes if they do not exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.executescript(SCHEMA)
