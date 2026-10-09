"""
TrustCheck FastAPI application entry point.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import (
    auth_router,
    dashboard_router,
    orders_router,
    payments_router,
    products_router,
    seller_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trustcheck")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TrustCheck API",
    description=(
        "Digital trust and fraud-risk assessment for social commerce sellers. "
        "Risk estimates only — not proof of payment."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router.router)
app.include_router(seller_router.router)
app.include_router(products_router.router)
app.include_router(orders_router.router)
app.include_router(payments_router.router)
app.include_router(dashboard_router.router)

@app.get("/api/health")
def health():
    from app.analysis.ocr_check import get_ocr_availability
    return {
        "status": "ok",
        "version": "1.0.0",
        "ocr": get_ocr_availability(),
    }


@app.get("/scam-checker.html")
def redirect_scam_checker():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard.html", status_code=301)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    logger.info("Initialising database …")
    init_db()
    logger.info("TrustCheck is ready.")

    # Warn about OCR availability
    from app.analysis.ocr_check import get_ocr_availability
    avail = get_ocr_availability()
    if not avail["tesseract"] and not avail["rapidocr"]:
        logger.warning(
            "No OCR engine found. "
            "Payment screenshot analysis will be unavailable. "
            "Install Tesseract: https://github.com/tesseract-ocr/tesseract "
            "or run: pip install rapidocr-onnxruntime"
        )
    else:
        active = [k for k, v in avail.items() if v and k in ("tesseract", "rapidocr")]
        logger.info("OCR engines available: %s", active)


