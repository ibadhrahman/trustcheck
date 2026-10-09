"""Unit tests for Gemini's structured payment extraction schema."""

from unittest.mock import AsyncMock

import pytest

from app.analysis import payment_extractor
from app.analysis.gemini_vision import (
    GeminiPaymentExtraction,
    gemini_extraction_to_fields_dict,
)


def test_gemini_confidence_schema_uses_fixed_fields():
    """Gemini Developer API does not accept JSON Schema additionalProperties."""
    schema = GeminiPaymentExtraction.model_json_schema()
    confidence_schema = schema["$defs"]["GeminiFieldConfidence"]

    assert "additionalProperties" not in confidence_schema
    assert "amount" in confidence_schema["properties"]
    assert "utr" in confidence_schema["properties"]


def test_gemini_confidence_fields_remain_a_dict_in_api_result():
    extraction = GeminiPaymentExtraction.model_validate(
        {
            "amount": 123.0,
            "utr": "123456789012",
            "field_confidence": {"amount": "medium", "utr": "high"},
        }
    )

    result = gemini_extraction_to_fields_dict(extraction)

    assert result["field_confidence"] == {"amount": "medium", "utr": "high"}
    assert result["ocr_confidence"] == 0.75
    assert result["engine_used"] == "gemini"


@pytest.mark.asyncio
async def test_gemini_is_used_after_deepseek_failure(monkeypatch):
    monkeypatch.setattr(payment_extractor.settings, "deepseek_enabled", True)
    monkeypatch.setattr(payment_extractor.settings, "gemini_enabled", True)
    monkeypatch.setattr(payment_extractor, "get_deepseek_async_client", lambda: object())
    monkeypatch.setattr(payment_extractor, "get_gemini_client", lambda: object())
    monkeypatch.setattr(
        payment_extractor,
        "analyze_payment_screenshot_deepseek_async",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        payment_extractor,
        "analyze_payment_screenshot_gemini_async",
        AsyncMock(return_value=GeminiPaymentExtraction(amount=123.0)),
    )
    local_ocr = AsyncMock(side_effect=AssertionError("OCR should not run after Gemini succeeds"))
    monkeypatch.setattr(payment_extractor, "extract_payment_fields", local_ocr)

    result = await payment_extractor.extract_payment_screenshot_details_async(b"synthetic image")

    assert result["engine_used"] == "gemini"
    assert result["amount"] == 123.0
    local_ocr.assert_not_called()
