"""
app/analysis/payment_extractor.py

Unified payment extraction pipeline for TrustCheck.
Prioritizes DeepSeek V4.1 Flash Multimodal AI, then uses Gemini when enabled,
and falls back to local multi-pass OCR (RapidOCR / Tesseract) if both are unavailable.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.analysis.deepseek_vision import (
    analyze_payment_screenshot_deepseek_async,
    analyze_payment_screenshot_deepseek_sync,
    deepseek_extraction_to_fields_dict,
    get_deepseek_async_client,
)
from app.analysis.gemini_vision import (
    analyze_payment_screenshot_gemini_async,
    analyze_payment_screenshot_gemini_sync,
    gemini_extraction_to_fields_dict,
    get_gemini_client,
)
from app.analysis.ocr_check import extract_payment_fields
from app.config import settings

logger = logging.getLogger(__name__)


async def extract_payment_screenshot_details_async(
    img_bytes: bytes,
    expected_amount: Optional[float] = None,
    expected_payee_name: Optional[str] = None,
) -> dict:
    """
    Primary asynchronous payment screenshot analysis entrypoint.
    1. Attempts DeepSeek V4.1 Flash Multimodal AI (single structured model request).
    2. Optional Gemini fallback if explicitly enabled and configured.
    3. Falls back to local OCR pipeline if AI models are unavailable or fail.
    """
    # 1. Attempt DeepSeek V4.1 Flash Multimodal Vision if client is available
    if settings.deepseek_enabled and get_deepseek_async_client() is not None:
        try:
            logger.info("Analyzing payment screenshot using DeepSeek Multimodal AI (%s)", settings.deepseek_model)
            deepseek_result = await analyze_payment_screenshot_deepseek_async(img_bytes=img_bytes)
            if deepseek_result is not None:
                return deepseek_extraction_to_fields_dict(deepseek_result)
            logger.warning("DeepSeek returned no result; trying Gemini fallback if enabled.")
        except Exception as exc:
            logger.warning("DeepSeek extraction error: %s; trying Gemini fallback if enabled.", type(exc).__name__)

    # 2. Optional Gemini fallback if enabled
    if getattr(settings, "gemini_enabled", False):
        try:
            if get_gemini_client() is not None:
                gemini_result = await analyze_payment_screenshot_gemini_async(
                    img_bytes=img_bytes,
                    expected_amount=expected_amount,
                    expected_payee_name=expected_payee_name,
                )
                if gemini_result is not None:
                    return gemini_extraction_to_fields_dict(gemini_result)
        except Exception as exc:
            logger.warning("Gemini fallback skipped: %s", type(exc).__name__)

    # 3. Fallback to local OCR pipeline
    logger.info("Analyzing payment screenshot using local OCR pipeline")
    local_result = extract_payment_fields(
        img_bytes=img_bytes,
        expected_amount=expected_amount,
        expected_payee_name=expected_payee_name,
    )
    local_result["engine_used"] = "local_ocr"
    return local_result


def extract_payment_screenshot_details_sync(
    img_bytes: bytes,
    expected_amount: Optional[float] = None,
    expected_payee_name: Optional[str] = None,
) -> dict:
    """
    Synchronous payment screenshot analysis entrypoint.
    """
    if settings.deepseek_enabled and get_deepseek_async_client() is not None:
        try:
            deepseek_result = analyze_payment_screenshot_deepseek_sync(img_bytes=img_bytes)
            if deepseek_result is not None:
                return deepseek_extraction_to_fields_dict(deepseek_result)
            logger.warning("DeepSeek returned no result; trying Gemini fallback if enabled.")
        except Exception as exc:
            logger.warning("DeepSeek sync extraction error: %s; trying Gemini fallback if enabled.", type(exc).__name__)

    if settings.gemini_enabled:
        try:
            if get_gemini_client() is not None:
                gemini_result = analyze_payment_screenshot_gemini_sync(
                    img_bytes=img_bytes,
                    expected_amount=expected_amount,
                    expected_payee_name=expected_payee_name,
                )
                if gemini_result is not None:
                    return gemini_extraction_to_fields_dict(gemini_result)
        except Exception as exc:
            logger.warning("Gemini sync fallback skipped: %s", type(exc).__name__)

    logger.info("Analyzing payment screenshot using local OCR pipeline")
    local_result = extract_payment_fields(
        img_bytes=img_bytes,
        expected_amount=expected_amount,
        expected_payee_name=expected_payee_name,
    )
    local_result["engine_used"] = "local_ocr"
    return local_result
