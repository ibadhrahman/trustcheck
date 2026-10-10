"""
TrustCheck FastAPI application entry point.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import init_db
from app.routers import (
    auth_router,
    dashboard_router,
    orders_router,
    outcomes_router,
    payments_router,
    products_router,
    seller_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trustcheck")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
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
    yield


app = FastAPI(
    title="TrustCheck API",
    description=(
        "Digital trust and fraud-risk assessment for social commerce sellers. "
        "Risk estimates only — not proof of payment."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
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
app.include_router(outcomes_router.router)
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
    return RedirectResponse(url="/dashboard.html", status_code=301)


@app.get("/products.html")
def redirect_products():
    return RedirectResponse(url="/dashboard.html", status_code=301)


# ---------------------------------------------------------------------------
# Static frontend & Custom 404
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    fav_path = _FRONTEND_DIR / "favicon.ico"
    if fav_path.exists():
        return FileResponse(fav_path, media_type="image/x-icon")
    logo_path = _FRONTEND_DIR / "logo.png"
    return FileResponse(logo_path, media_type="image/png")


@app.get("/404.html", include_in_schema=False)
def get_404_page():
    page_404 = _FRONTEND_DIR / "404.html"
    if page_404.exists():
        return FileResponse(page_404, status_code=404)
    return JSONResponse({"detail": "Page not found"}, status_code=404)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail or "Not Found"}, status_code=404)
        page_404 = _FRONTEND_DIR / "404.html"
        if page_404.exists():
            return FileResponse(page_404, status_code=404)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(path: str):
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")



# ---------------------------------------------------------------------------


