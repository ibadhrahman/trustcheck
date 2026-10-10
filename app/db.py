"""
Database engine, session factory, and Base.
All models import Base from here.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

def _database_url() -> URL | str:
    """Normalize Supabase/PostgreSQL URLs for SQLAlchemy's psycopg 3 driver."""
    raw_url = settings.database_url.strip()
    if raw_url.startswith("postgres://"):
        raw_url = "postgresql://" + raw_url.removeprefix("postgres://")

    if not raw_url.startswith("postgresql"):
        return raw_url

    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")

    host = (url.host or "").lower()
    if "supabase" in host and "sslmode" not in url.query:
        url = url.update_query_dict({"sslmode": "require"})
    return url


database_url = _database_url()
is_sqlite = str(database_url).startswith("sqlite")

# SQLite-specific connect_args for thread safety in dev and tests.
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def _upgrade_sqlite_anonymous_outcomes() -> None:
    """Allow buyer outcomes without accounts while preserving existing SQLite rows."""
    raw_connection = engine.raw_connection()
    driver: Any = getattr(raw_connection, "driver_connection", None)
    if driver is None:
        raw_connection.close()
        return
    foreign_keys_enabled = driver.execute("PRAGMA foreign_keys").fetchone()[0]
    try:
        columns = {
            row[1]: row[3]
            for row in driver.execute("PRAGMA table_info(order_outcomes)").fetchall()
        }
        if not columns or not (columns.get("buyer_id") or columns.get("buyer_received_at")):
            return

        driver.execute("PRAGMA foreign_keys=OFF")
        driver.execute("BEGIN IMMEDIATE")
        driver.execute("""
            CREATE TABLE order_outcomes_new (
                id INTEGER NOT NULL PRIMARY KEY,
                order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
                buyer_id INTEGER REFERENCES buyer_accounts(id),
                outcome VARCHAR(30) NOT NULL,
                reason VARCHAR(40),
                description TEXT,
                status VARCHAR(30) NOT NULL,
                reported_at DATETIME,
                buyer_received_at DATETIME,
                problem_reported_at DATETIME,
                response_deadline DATETIME,
                seller_resolution_type VARCHAR(30),
                seller_response TEXT,
                seller_responded_at DATETIME,
                resolved_at DATETIME
            )
        """)
        driver.execute("""
            INSERT INTO order_outcomes_new (
                id, order_id, buyer_id, outcome, reason, description, status,
                reported_at, buyer_received_at, problem_reported_at,
                response_deadline, seller_resolution_type, seller_response,
                seller_responded_at, resolved_at
            )
            SELECT
                id, order_id, buyer_id, outcome, reason, description, status,
                reported_at, buyer_received_at, problem_reported_at,
                response_deadline, seller_resolution_type, seller_response,
                seller_responded_at, resolved_at
            FROM order_outcomes
        """)
        driver.execute("DROP TABLE order_outcomes")
        driver.execute("ALTER TABLE order_outcomes_new RENAME TO order_outcomes")
        driver.execute("CREATE INDEX ix_order_outcomes_id ON order_outcomes (id)")
        driver.execute("CREATE INDEX ix_order_outcomes_buyer ON order_outcomes (buyer_id)")
        driver.execute("CREATE INDEX ix_order_outcomes_status ON order_outcomes (status)")
        driver.commit()
    except Exception:
        driver.rollback()
        raise
    finally:
        try:
            driver.execute(f"PRAGMA foreign_keys={1 if foreign_keys_enabled else 0}")
        finally:
            raw_connection.close()


def get_db():
    """FastAPI dependency: yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called at application startup."""
    # Import all models so SQLAlchemy registers them
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            res = conn.execute(text("PRAGMA table_info(payment_submissions)"))
            existing_cols = {row[1] for row in res.fetchall()}
            new_columns = {
                "extracted_json": "TEXT",
                "forensics_json": "TEXT",
                "duplicate_json": "TEXT",
                "comparison_json": "TEXT",
            }
            for column_name, column_type in new_columns.items():
                if column_name not in existing_cols:
                    conn.execute(text(
                        f"ALTER TABLE payment_submissions ADD COLUMN {column_name} {column_type}"
                    ))
            order_cols = {
                row[1] for row in conn.execute(text("PRAGMA table_info(orders)")).fetchall()
            }
            if "buyer_id" not in order_cols:
                conn.execute(text(
                    "ALTER TABLE orders ADD COLUMN buyer_id INTEGER REFERENCES buyer_accounts(id)"
                ))
            if "buyer_access_hmac" not in order_cols:
                conn.execute(text("ALTER TABLE orders ADD COLUMN buyer_access_hmac VARCHAR(64)"))
            outcome_cols = {
                row[1] for row in conn.execute(text("PRAGMA table_info(order_outcomes)")).fetchall()
            }
            if outcome_cols and "buyer_received_at" not in outcome_cols:
                conn.execute(text("ALTER TABLE order_outcomes ADD COLUMN buyer_received_at DATETIME"))
                conn.execute(text("UPDATE order_outcomes SET buyer_received_at = reported_at WHERE buyer_received_at IS NULL"))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_buyer_access_hmac ON orders (buyer_access_hmac)"
            ))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_buyer_id ON orders (buyer_id)"))
        elif engine.dialect.name == "postgresql":
            # Apply the compatibility columns in one round trip to hosted Postgres.
            conn.execute(text("""
                DO $trustcheck_schema$
                BEGIN
                    ALTER TABLE public.payment_submissions ADD COLUMN IF NOT EXISTS extracted_json TEXT;
                    ALTER TABLE public.payment_submissions ADD COLUMN IF NOT EXISTS forensics_json TEXT;
                    ALTER TABLE public.payment_submissions ADD COLUMN IF NOT EXISTS duplicate_json TEXT;
                    ALTER TABLE public.payment_submissions ADD COLUMN IF NOT EXISTS comparison_json TEXT;
                    ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS buyer_id INTEGER REFERENCES public.buyer_accounts(id);
                    ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS buyer_access_hmac VARCHAR(64);
                    ALTER TABLE public.order_outcomes ADD COLUMN IF NOT EXISTS buyer_received_at TIMESTAMP WITHOUT TIME ZONE;
                    UPDATE public.order_outcomes SET buyer_received_at = reported_at WHERE buyer_received_at IS NULL;
                    ALTER TABLE public.order_outcomes ALTER COLUMN buyer_id DROP NOT NULL;
                    ALTER TABLE public.order_outcomes ALTER COLUMN buyer_received_at DROP NOT NULL;
                END;
                $trustcheck_schema$;
            """))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_buyer_access_hmac ON public.orders (buyer_access_hmac)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_buyer_id ON public.orders (buyer_id)"))

    if engine.dialect.name == "sqlite":
        _upgrade_sqlite_anonymous_outcomes()

    _secure_supabase_tables()


def _secure_supabase_tables() -> None:
    """Keep TrustCheck tables private from Supabase's browser-facing Data API."""
    host = (engine.url.host or "").lower()
    if engine.dialect.name != "postgresql" or "supabase" not in host:
        return

    # The app uses its own authenticated FastAPI backend and connects server-side.
    # It does not use Supabase's anon/authenticated Data API roles.
    table_names = ", ".join(
        "'" + table_name.replace("'", "''") + "'"
        for table_name in Base.metadata.tables
    )
    # Keep the same RLS and privilege rules while avoiding one network round trip
    # per table when the app connects to hosted Supabase during startup.
    with engine.begin() as conn:
        conn.execute(text(f"""
            DO $trustcheck_security$
            DECLARE
                table_name text;
            BEGIN
                FOREACH table_name IN ARRAY ARRAY[{table_names}] LOOP
                    EXECUTE format(
                        'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
                        table_name
                    );
                    EXECUTE format(
                        'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC, anon, authenticated',
                        table_name
                    );
                END LOOP;
                EXECUTE 'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated';
                EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated';
            END;
            $trustcheck_security$;
        """))
