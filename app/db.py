"""
Database engine, session factory, and Base.
All models import Base from here.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# SQLite-specific connect_args for thread safety in dev
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
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

    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            res = conn.execute(text("PRAGMA table_info(payment_submissions)"))
            existing_cols = {row[1] for row in res.fetchall()}
            if existing_cols:
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
                conn.commit()
        except Exception:
            pass
