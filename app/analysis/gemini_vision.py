"""
app/analysis/gemini_vision.py

Gemini Multimodal AI integration for payment screenshot understanding.
Uses Google's official Python SDK (google-genai) to analyze screenshots directly,
extracting amounts, UTRs, transaction IDs, payee details, and viewpoints
with structured output validation and zero image persistence.
"""
from __future__ import annotations

import io
import json
import logging
from typing import Optional

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structured Output Schema
# ---------------------------------------------------------------------------

class GeminiFieldConfidence(BaseModel):
    """Fixed-key confidence schema supported by Gemini structured output."""

    amount: Optional[str] = None
    currency: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_upi_id: Optional[str] = None
    transaction_id: Optional[str] = None
    utr: Optional[str] = None
    transaction_date: Optional[str] = None
    transaction_time: Optional[str] = None
    payment_app: Optional[str] = None
    payment_status_text: Optional[str] = None
    payment_perspective: Optional[str] = None


class GeminiPaymentExtraction(BaseModel):
    """
    Strict structured output schema for multimodal payment screenshot analysis.
    """
    amount: Optional[float] = Field(
        default=None,
        description="Exact monetary transaction amount transferred/paid. Must be null if unreadable, ambiguous, or not visible.",
    )
    currency: Optional[str] = Field(
        default="INR",
        description="Currency symbol or ISO code, typically 'INR' or '₹'.",
    )
    receiver_name: Optional[str] = Field(
        default=None,
        description="Name of the payee, merchant, or beneficiary receiving funds.",
    )
    receiver_upi_id: Optional[str] = Field(
        default=None,
        description="UPI ID / VPA of payee/receiver if visible (e.g. name@okhdfcbank).",
    )
    transaction_id: Optional[str] = Field(
        default=None,
        description="Specific transaction identifier (e.g. PhonePe T26..., Google Pay Txn ID).",
    )
    utr: Optional[str] = Field(
        default=None,
        description="12-digit UPI reference number or bank UTR.",
    )
    transaction_date: Optional[str] = Field(
        default=None,
        description="Date of payment as displayed (e.g. '09 Oct 2026' or '2026-10-09').",
    )
    transaction_time: Optional[str] = Field(
        default=None,
        description="Time of payment as displayed (e.g. '16:47' or '04:47 PM').",
    )
    payment_app: Optional[str] = Field(
        default=None,
        description="Identified payment app: 'Google Pay', 'PhonePe', 'Paytm', 'BHIM', 'Cred', or other.",
    )
    payment_status_text: Optional[str] = Field(
        default=None,
        description="Exact visible payment status text: 'Completed', 'Payment Successful', 'Paid', etc.",
    )
    payment_perspective: str = Field(
        default="unknown",
        description="'payer' if screenshot represents payment made/debited, 'receiver' if payment received/credited, or 'unknown'.",
    )
    raw_amount_text: Optional[str] = Field(
        default=None,
        description="Exact raw text for amount as displayed on screen, e.g. '₹1,250.00' or '₹10'.",
    )
    field_confidence: GeminiFieldConfidence = Field(
        default_factory=GeminiFieldConfidence,
        description="Confidence per extracted field: 'high', 'medium', 'low', or 'unknown'.",
    )
    uncertain_fields: list[str] = Field(
        default_factory=list,
        description="List of fields that were ambiguous, partially occluded, or uncertain.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Extraction anomalies, multiple monetary numbers, or potential red flags seen.",
    )


# ---------------------------------------------------------------------------
# Gemini Client Singleton & Lifecycle
# ---------------------------------------------------------------------------

_cached_client = None
_cached_client_key: Optional[str] = None


def get_gemini_client():
    """
    Initializes and reuses the google-genai Client.
    Configures timeout from settings.gemini_timeout_seconds.
    Returns None if gemini_api_key is not configured or gemini_enabled is False.
    """
    global _cached_client, _cached_client_key

    if not settings.gemini_enabled:
        return None

    api_key = (settings.gemini_api_key or "").strip()
    if not api_key:
        return None

    if _cached_client is not None and _cached_client_key == api_key:
        return _cached_client

    try:
        from google import genai
        from google.genai import types

        timeout_ms = max(1000, settings.gemini_timeout_seconds * 1000)
        http_options = types.HttpOptions(timeout=timeout_ms)

        client = genai.Client(api_key=api_key, http_options=http_options)
        _cached_client = client
        _cached_client_key = api_key
        return client
    except Exception as exc:
        logger.warning("Failed to initialize Gemini client: %s", type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# Image Preprocessing & Optimization
# ---------------------------------------------------------------------------

def optimize_image_for_gemini(img_bytes: bytes, max_dimension: int = 1280) -> tuple[bytes, str]:
    """
    Validates, corrects EXIF orientation, and proportionally downscales large
    screenshots to max_dimension in memory (io.BytesIO) to minimize network payload
    and processing latency without degrading character clarity.
    Returns (optimized_jpeg_bytes, 'image/jpeg').
    """
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(img_bytes))
        # Correct orientation from mobile camera/screenshot metadata
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")

        w, h = img.size
        if max(w, h) > max_dimension:
            scale = max_dimension / max(w, h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            resample = getattr(getattr(Image, "Resampling", None), "LANCZOS", getattr(Image, "LANCZOS", 1))
            img = img.resize((new_w, new_h), resample)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.debug("Image optimization fallback: %s", type(exc).__name__)
        return img_bytes, "image/jpeg"


# ---------------------------------------------------------------------------
# Multimodal Prompt Construction
# ---------------------------------------------------------------------------

GEMINI_PAYMENT_SYSTEM_PROMPT = """You are a senior cybersecurity multimodal payment analysis engine for TrustCheck.
Your task is to analyze mobile payment confirmation screenshots (UPI, Google Pay, PhonePe, Paytm, BHIM, etc.) with high precision.

CRITICAL AMOUNT RECOGNITION RULES:
1. Extract the actual payment transaction amount that was transferred/paid.
2. Read the prominent transaction value carefully. Distinguish ₹1, ₹10, ₹100, ₹210, ₹400, ₹1000, ₹1250 without omitting or inserting digits.
3. NEVER mistake bank balances, cashback rewards, wallet limits, transaction fees, or time/battery indicators for the transfer amount.
4. If multiple amounts appear, extract the primary transferred sum and note any ambiguity in uncertain_fields and warnings.
5. If the amount is unreadable or ambiguous, set amount to null. NEVER guess.
6. Store the exact raw textual characters for the amount in raw_amount_text (e.g. '₹1,250.00').

TRANSACTION & PAYEE DETAILS:
1. Payee/Receiver: Extract the merchant or recipient name and their UPI ID (VPA) if displayed.
2. UTR / Transaction ID:
   - PhonePe typically has a 22-character PhonePe transaction ID (starts with T) and a 12-digit UTR.
   - Google Pay and BHIM have a 12-digit UPI Transaction ID / UTR.
   - Paytm displays a 12-digit UPI Ref ID or Order ID.
   - If a transaction ID or UTR is not present, set it to null. NEVER invent numbers.
3. Perspective:
   - Set 'payer' if the screen shows money sent, debited, or paid out by the user.
   - Set 'receiver' if the screen shows money received or credited into an account.
   - Set 'unknown' if unclear.
4. Confidence: Provide confidence ('high', 'medium', 'low') for extracted fields.
"""


# ---------------------------------------------------------------------------
# Multimodal Analysis Execution
# ---------------------------------------------------------------------------

async def analyze_payment_screenshot_gemini_async(
    img_bytes: bytes,
    expected_amount: Optional[float] = None,
    expected_payee_name: Optional[str] = None,
) -> Optional[GeminiPaymentExtraction]:
    """
    Executes a single structured multimodal request to Gemini asynchronously.
    Returns GeminiPaymentExtraction on success, or None on failure/unconfigured.
    """
    client = get_gemini_client()
    if client is None:
        return None

    try:
        from google.genai import types

        optimized_bytes, mime_type = optimize_image_for_gemini(img_bytes)

        image_part = types.Part.from_bytes(
            data=optimized_bytes,
            mime_type=mime_type,
        )

        user_content = (
            "Analyze this payment screenshot and extract all transaction details. "
            "Follow the strict amount rules and return structured JSON matching the schema."
        )

        config = types.GenerateContentConfig(
            system_instruction=GEMINI_PAYMENT_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GeminiPaymentExtraction,
            temperature=0.0,
        )

        model_name = settings.gemini_model or "gemini-2.5-flash"

        response = await client.aio.models.generate_content(
            model=model_name,
            contents=[image_part, user_content],
            config=config,
        )

        if not response or not response.text:
            logger.warning("Gemini returned empty response text.")
            return None

        # Parse response into GeminiPaymentExtraction
        raw_text = response.text.strip()
        data = json.loads(raw_text)
        extraction = GeminiPaymentExtraction.model_validate(data)
        return extraction

    except Exception as exc:
        logger.warning("Gemini multimodal analysis failed: %s", type(exc).__name__)
        return None


def analyze_payment_screenshot_gemini_sync(
    img_bytes: bytes,
    expected_amount: Optional[float] = None,
    expected_payee_name: Optional[str] = None,
) -> Optional[GeminiPaymentExtraction]:
    """
    Synchronous version of Gemini multimodal analysis.
    """
    client = get_gemini_client()
    if client is None:
        return None

    try:
        from google.genai import types

        optimized_bytes, mime_type = optimize_image_for_gemini(img_bytes)

        image_part = types.Part.from_bytes(
            data=optimized_bytes,
            mime_type=mime_type,
        )

        user_content = (
            "Analyze this payment screenshot and extract all transaction details. "
            "Follow the strict amount rules and return structured JSON matching the schema."
        )

        config = types.GenerateContentConfig(
            system_instruction=GEMINI_PAYMENT_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GeminiPaymentExtraction,
            temperature=0.0,
        )

        model_name = settings.gemini_model or "gemini-2.5-flash"

        response = client.models.generate_content(
            model=model_name,
            contents=[image_part, user_content],
            config=config,
        )

        if not response or not response.text:
            return None

        data = json.loads(response.text.strip())
        return GeminiPaymentExtraction.model_validate(data)
    except Exception as exc:
        logger.warning("Gemini sync analysis failed: %s", type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# Adapter to TrustCheck unified extraction dict
# ---------------------------------------------------------------------------

def gemini_extraction_to_fields_dict(ext: GeminiPaymentExtraction) -> dict:
    """
    Converts GeminiPaymentExtraction into the standardized dict format expected
    by TrustCheck's _compute_risk, duplicate detection, and API response models.
    """
    # Primary transaction identifier prefers UTR or tx_id
    tx_id_primary = ext.transaction_id or ext.utr
    utr_primary = ext.utr or ext.transaction_id

    # Estimate overall confidence based on amount and tx ID confidence
    conf_map = {"high": 0.95, "medium": 0.75, "low": 0.4, "unknown": 0.3}
    field_confidence = ext.field_confidence.model_dump(exclude_none=True)
    amount_conf = conf_map.get(field_confidence.get("amount", "high"), 0.9)

    return {
        "amount": ext.amount,
        "currency": ext.currency or "INR",
        "tx_id": tx_id_primary,
        "utr": utr_primary,
        "payee_name": ext.receiver_name,
        "payee_upi_id": ext.receiver_upi_id,
        "date_str": ext.transaction_date,
        "time_str": ext.transaction_time,
        "app_indicator": ext.payment_app,
        "status_text": ext.payment_status_text,
        "viewpoint": ext.payment_perspective or "unknown",
        "raw_amount_text": ext.raw_amount_text,
        "field_confidence": field_confidence,
        "uncertain_fields": ext.uncertain_fields,
        "warnings": ext.warnings,
        "ocr_confidence": amount_conf,
        "engine_used": "gemini",
    }
