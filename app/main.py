"""TrustCheck FastAPI application shell."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import router as auth_router
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


@app.exception_handler(StarletteHTTPException)
async def http_exception_response(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Keep API and framework HTTP errors in the contract's error shape."""
    if isinstance(exc.detail, str):
        message = exc.detail
    elif isinstance(exc.detail, dict) and isinstance(exc.detail.get("error"), str):
        message = exc.detail["error"]
    else:
        message = "The request could not be completed."
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": message},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_response(_: Request, __: RequestValidationError) -> JSONResponse:
    """Return a concise error body for malformed request data."""
    return JSONResponse(
        status_code=422,
        content={"error": "Request data is invalid or missing required fields."},
    )


app.include_router(auth_router)


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
