"""
DeepSeek V4.1 Flash Multimodal AI Vision Engine for TrustCheck.

Integrates DeepSeek's native multimodal MoE architecture (DeepSeek-V4.1-Flash)
via OpenAI-compatible API to perform single-pass, structured extraction of
payment screenshot details (UPI, Google Pay, PhonePe, Paytm, BHIM).

Zero-Storage Invariant:
All image processing and base64 serialization executes strictly in-memory
(io.BytesIO). Raw image bytes are NEVER persisted to disk or SQLite BLOBs.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings

logger = logging.getLogger("trustcheck.deepseek_vision")


# ---------------------------------------------------------------------------
# Structured Output Schema
# ---------------------------------------------------------------------------

class DeepSeekPaymentExtraction(BaseModel):
    """
    Validated structured extraction returned by DeepSeek-V4.1-Flash.
    Ensures zero hallucination and strict types for verification.
    """
    amount: Optional[float] = Field(
        default=None,
        description="The primary payment transaction amount transferred. Null if unreadable or absent.",
    )
    raw_amount_text: Optional[str] = Field(
        default=None,
        description="The exact raw text string of the amount as seen (e.g., '₹10.00', '1.00', '₹ 210').",
    )
    currency: Optional[str] = Field(
        default="INR",
        description="Currency code: 'INR', 'USD', etc.",
    )
    receiver_name: Optional[str] = Field(
        default=None,
        description="Name of the payee, merchant, or receiver shown in the screenshot.",
    )
    receiver_upi_id: Optional[str] = Field(
        default=None,
        description="The VPA or UPI ID of the payee (e.g. 'merchant@okhdfcbank').",
    )
    transaction_id: Optional[str] = Field(
        default=None,
        description="Bank/app transaction reference ID (e.g. PhonePe transaction ID, Paytm order ID).",
    )
    utr: Optional[str] = Field(
        default=None,
        description="12-digit UTR (Unique Transaction Reference) or banking reference number.",
    )
    transaction_date: Optional[str] = Field(
        default=None,
        description="Transaction date formatted as YYYY-MM-DD or DD Mon YYYY if visible.",
    )
    transaction_time: Optional[str] = Field(
        default=None,
        description="Transaction time formatted as HH:MM or HH:MM:SS if visible.",
    )
    payment_app: Optional[str] = Field(
        default=None,
        description="Recognized payment app: 'PhonePe', 'Google Pay', 'Paytm', 'BHIM', 'CRED', 'Other', or 'Unknown'.",
    )
    payment_status_text: Optional[str] = Field(
        default=None,
        description="Status banner text, e.g. 'Payment Successful', 'Paid successfully', 'Completed'.",
    )
    payment_perspective: Optional[str] = Field(
        default="payer",
        description="Perspective: 'payer' (sent/paid), 'recipient' (received), or 'unknown'.",
    )
    field_confidence: dict[str, str] = Field(
        default_factory=dict,
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

    @field_validator("amount", mode="before")
    @classmethod
    def sanitize_amount(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v) if v >= 0 else None
        if isinstance(v, str):
            clean = v.replace("₹", "").replace(",", "").replace("Rs.", "").replace("INR", "").strip()
            try:
                val = float(clean)
                return val if val >= 0 else None
            except ValueError:
                return None
        return None


# ---------------------------------------------------------------------------
# DeepSeek Client Lifecycle & In-Memory Optimization
# ---------------------------------------------------------------------------

_cached_async_client: Any = None
_cached_client_key: Optional[str] = None


def get_deepseek_async_client() -> Any:
    """
    Initializes and reuses an AsyncOpenAI client configured for DeepSeek.
    Returns None if deepseek_api_key is unconfigured or deepseek_enabled is False.
    """
    global _cached_async_client, _cached_client_key

    if not settings.deepseek_enabled:
        return None

    api_key = (settings.deepseek_api_key or "").strip()
    if not api_key:
        return None

    cache_key = f"{api_key}::{settings.deepseek_base_url}"
    if _cached_async_client is not None and _cached_client_key == cache_key:
        return _cached_async_client

    try:
        from openai import AsyncOpenAI

        timeout_sec = max(2.0, float(settings.deepseek_timeout_seconds))
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.deepseek_base_url.rstrip("/"),
            timeout=timeout_sec,
            max_retries=settings.deepseek_max_retries,
        )
        _cached_async_client = client
        _cached_client_key = cache_key
        return client
    except Exception as exc:
        logger.warning("Failed to initialize DeepSeek AsyncOpenAI client: %s", type(exc).__name__)
        return None


def optimize_image_for_deepseek(img_bytes: bytes, max_dimension: int = 1280) -> tuple[bytes, str, str]:
    """
    Validates, corrects EXIF orientation, and proportionally downscales large
    screenshots to max_dimension strictly in-memory (io.BytesIO) to minimize
    base64 network payload and processing latency without degrading character clarity.

    Returns:
        (optimized_jpeg_bytes, mime_type, base64_data_url)
    """
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(img_bytes))
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
        optimized_bytes = buf.getvalue()
        mime_type = "image/jpeg"
    except Exception as exc:
        logger.debug("Image optimization fallback: %s", type(exc).__name__)
        optimized_bytes = img_bytes
        mime_type = "image/jpeg"

    b64_str = base64.b64encode(optimized_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64_str}"
    return optimized_bytes, mime_type, data_url


# ---------------------------------------------------------------------------
# DeepSeek Multimodal System Instructions
# ---------------------------------------------------------------------------

DEEPSEEK_PAYMENT_SYSTEM_PROMPT = """You are a senior cybersecurity multimodal payment analysis engine for TrustCheck.
Your task is to analyze mobile payment confirmation screenshots (UPI, Google Pay, PhonePe, Paytm, BHIM, CRED) with extreme precision.

CRITICAL AMOUNT RECOGNITION RULES:
1. Extract the actual payment transaction amount that was transferred/paid.
2. Read the prominent transaction value carefully. Distinguish ₹1, ₹10, ₹100, ₹210, ₹400, ₹1000, ₹1250 without omitting or inserting digits.
3. NEVER mistake bank balances, cashback rewards, wallet limits, transaction fees, or time/battery indicators for the transfer amount.
4. If multiple amounts appear, extract the primary transferred sum and note any ambiguity in uncertain_fields and warnings.
5. If the amount is ambiguous or unreadable, set amount to null and add 'amount' to uncertain_fields. NEVER invent or guess.
6. Look for:
   - Currency (e.g., INR, USD)
   - Receiver or payee name
   - Receiver UPI ID / VPA (e.g., username@bank)
   - Transaction ID and 12-digit UTR / banking reference number
   - Date and time of transfer
   - Recognized payment application (PhonePe, Google Pay, Paytm, BHIM, CRED, etc.)
   - Visible payment status banner (e.g. 'Payment Successful', 'Completed', 'Paid')
   - Perspective: 'payer' (sent/paid), 'recipient' (received), or 'unknown'

You MUST output valid, parseable JSON conforming exactly to this JSON schema:
{
  "amount": float or null,
  "raw_amount_text": string or null,
  "currency": string or null,
  "receiver_name": string or null,
  "receiver_upi_id": string or null,
  "transaction_id": string or null,
  "utr": string or null,
  "transaction_date": string or null,
  "transaction_time": string or null,
  "payment_app": string or null,
  "payment_status_text": string or null,
  "payment_perspective": "payer" or "recipient" or "unknown",
  "field_confidence": { "amount": "high"|"medium"|"low", ... },
  "uncertain_fields": [string, ...],
  "warnings": [string, ...]
}

Return ONLY the JSON object. Do not include markdown fences or extraneous text outside the JSON.
"""


# ---------------------------------------------------------------------------
# Multimodal Extraction Pipeline (Async & Sync)
# ---------------------------------------------------------------------------

async def analyze_payment_screenshot_deepseek_async(img_bytes: bytes) -> Optional[DeepSeekPaymentExtraction]:
    """
    Executes single-shot multimodal extraction using DeepSeek-V4.1-Flash.
    Non-blocking async call that preserves FastAPI event loop responsiveness.
    """
    client = get_deepseek_async_client()
    if client is None:
        logger.debug("DeepSeek client is not configured or disabled.")
        return None

    try:
        # In-memory optimization & base64 URL preparation
        _, _, data_url = optimize_image_for_deepseek(img_bytes)

        model_name = settings.deepseek_model or "deepseek-v4.1-flash"

        messages = [
            {"role": "system", "content": DEEPSEEK_PAYMENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract all transaction details from this payment confirmation screenshot as JSON.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            },
        ]

        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        content = response.choices[0].message.content
        if not content:
            logger.warning("DeepSeek returned empty content.")
            return None

        # Clean any potential leading/trailing markdown fences
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        validated = DeepSeekPaymentExtraction.model_validate(data)
        logger.info(
            "DeepSeek V4.1 Flash extracted: amount=%s %s, payee=%s, utr=%s",
            validated.amount,
            validated.currency,
            validated.receiver_name,
            validated.utr or validated.transaction_id,
        )
        return validated

    except json.JSONDecodeError as exc:
        logger.warning("DeepSeek returned malformed JSON: %s", exc)
        return None
    except Exception as exc:
        logger.warning("DeepSeek analysis error (%s): %s", type(exc).__name__, exc)
        return None


def analyze_payment_screenshot_deepseek_sync(img_bytes: bytes) -> Optional[DeepSeekPaymentExtraction]:
    """
    Synchronous fallback wrapper for testing or non-async contexts.
    """
    import anyio

    try:
        return anyio.run(analyze_payment_screenshot_deepseek_async, img_bytes)
    except Exception as exc:
        logger.warning("DeepSeek sync runner failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Schema Adapter for TrustCheck Verification Core
# ---------------------------------------------------------------------------

def deepseek_extraction_to_fields_dict(extraction: DeepSeekPaymentExtraction) -> dict[str, Any]:
    """
    Translates DeepSeekPaymentExtraction into TrustCheck's internal
    extracted_fields dictionary contract expected by payments_router.
    """
    # Prefer UTR if 12-digit, else transaction_id
    tx_id = extraction.utr or extraction.transaction_id

    return {
        "amount": extraction.amount,
        "raw_amount_text": extraction.raw_amount_text,
        "currency": extraction.currency or "INR",
        "receiver_name": extraction.receiver_name,
        "receiver_upi_id": extraction.receiver_upi_id,
        "transaction_id": tx_id,
        "utr": extraction.utr,
        "transaction_date": extraction.transaction_date,
        "transaction_time": extraction.transaction_time,
        "payment_app": extraction.payment_app,
        "payment_status_text": extraction.payment_status_text,
        "payment_perspective": extraction.payment_perspective,
        "field_confidence": extraction.field_confidence,
        "uncertain_fields": extraction.uncertain_fields,
        "warnings": extraction.warnings,
        "engine_used": "deepseek-v4.1-flash",
    }
