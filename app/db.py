"""
Database engine, session factory, and Base.
All models import Base from here.
"""
from __future__ import annotations

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
        elif engine.dialect.name == "postgresql":
            for column_name in (
                "extracted_json",
                "forensics_json",
                "duplicate_json",
                "comparison_json",
            ):
                conn.execute(text(
                    "ALTER TABLE payment_submissions "
                    f"ADD COLUMN IF NOT EXISTS {column_name} TEXT"
                ))

    _secure_supabase_tables()


def _secure_supabase_tables() -> None:
    """Keep TrustCheck tables private from Supabase's browser-facing Data API."""
    host = (engine.url.host or "").lower()
    if engine.dialect.name != "postgresql" or "supabase" not in host:
        return

    # The app uses its own authenticated FastAPI backend and connects server-side.
    # It does not use Supabase's anon/authenticated Data API roles.
    with engine.begin() as conn:
        for table_name in Base.metadata.tables:
            conn.execute(text(
                f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY'
            ))
            conn.execute(text(
                f'REVOKE ALL PRIVILEGES ON TABLE public."{table_name}" '
                "FROM PUBLIC, anon, authenticated"
            ))
        conn.execute(text(
            "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public "
            "FROM PUBLIC, anon, authenticated"
        ))
        conn.execute(text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated"
        ))
