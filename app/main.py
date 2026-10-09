"""TrustCheck FastAPI application shell."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import init_db


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize the local SQLite schema when the application starts."""
    init_db()
    yield


app = FastAPI(
    title="TrustCheck API",
    version="2.0.0",
    description="A verified order layer for Instagram and WhatsApp sellers.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", include_in_schema=False)
def health() -> dict[str, str]:
    """Return a small process-health response without adding contract docs."""
    return {"status": "ok"}


# Keep this catch-all mount after API routes so it does not shadow them.
app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend",
)
