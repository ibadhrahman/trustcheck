"""
Unit and integration tests for DeepSeek V4.1 Flash Multimodal AI Vision engine.
Tests schema validation, amount sanitization, payment app layouts,
error handling, and zero-storage compliance.
"""
import io
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.analysis.deepseek_vision import (
    DeepSeekPaymentExtraction,
    analyze_payment_screenshot_deepseek_async,
    deepseek_extraction_to_fields_dict,
    get_deepseek_async_client,
    optimize_image_for_deepseek,
)
from app.analysis.payment_extractor import extract_payment_screenshot_details_async
from app.config import settings
from app.models import Order
from app.referral_codes import create_order_referral_code


def _make_dummy_image(size=(300, 600)) -> bytes:
    img = Image.new("RGB", size, color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_deepseek_extraction_schema_validation():
    """Validates structured schema parsing and amount string cleansing."""
    raw = {
        "amount": "₹ 210.50",
        "raw_amount_text": "₹ 210.50",
        "currency": "INR",
        "receiver_name": "Rohan Handlooms",
        "receiver_upi_id": "rohan@okhdfcbank",
        "transaction_id": "T2610091647498994259007",
        "utr": "561219197980",
        "transaction_date": "2026-10-09",
        "transaction_time": "16:47",
        "payment_app": "PhonePe",
        "payment_status_text": "Payment Successful",
        "payment_perspective": "payer",
        "field_confidence": {"amount": "high", "utr": "high"},
        "uncertain_fields": [],
        "warnings": [],
    }
    extracted = DeepSeekPaymentExtraction.model_validate(raw)
    assert extracted.amount == 210.50
    assert extracted.currency == "INR"
    assert extracted.utr == "561219197980"
    assert extracted.payment_app == "PhonePe"

    # Test dictionary translation
    d = deepseek_extraction_to_fields_dict(extracted)
    assert d["amount"] == 210.50
    assert d["engine_used"] == "deepseek-v4.1-flash"
    assert d["transaction_id"] == "561219197980"


def test_deepseek_amount_distinction_and_no_digit_drop():
    """Ensures amounts like ₹210 are never truncated to ₹10 or ₹0."""
    raw_210 = {"amount": "210.00", "currency": "INR"}
    assert DeepSeekPaymentExtraction.model_validate(raw_210).amount == 210.0

    raw_1000 = {"amount": "₹ 1,000", "currency": "INR"}
    assert DeepSeekPaymentExtraction.model_validate(raw_1000).amount == 1000.0

    raw_decimals = {"amount": "0.50", "currency": "INR"}
    assert DeepSeekPaymentExtraction.model_validate(raw_decimals).amount == 0.50


def test_deepseek_unreadable_amount_handling():
    """Unreadable or ambiguous amounts must evaluate to None and be flagged."""
    raw = {
        "amount": None,
        "currency": "INR",
        "uncertain_fields": ["amount"],
        "warnings": ["Amount partially occluded by notification banner"],
    }
    extracted = DeepSeekPaymentExtraction.model_validate(raw)
    assert extracted.amount is None
    assert "amount" in extracted.uncertain_fields


def test_optimize_image_for_deepseek_dimensions_and_base64():
    """Verifies that large screenshots are downscaled in-memory and base64 formatted."""
    large_img = _make_dummy_image(size=(1800, 3200))
    opt_bytes, mime, data_url = optimize_image_for_deepseek(large_img, max_dimension=1280)

    assert mime == "image/jpeg"
    assert data_url.startswith("data:image/jpeg;base64,")
    assert len(opt_bytes) < len(large_img)

    # Check that reconstructed image does not exceed 1280
    decoded = Image.open(io.BytesIO(opt_bytes))
    assert max(decoded.size) <= 1280


@pytest.mark.asyncio
async def test_deepseek_phonepe_sample_extraction():
    """Simulates extraction on reference sample PhonePe: ₹10, UTR 561219197980."""
    mock_payload = {
        "amount": 10.0,
        "raw_amount_text": "₹10",
        "currency": "INR",
        "receiver_name": "Priya Crafts",
        "receiver_upi_id": "priyacrafts@ybl",
        "transaction_id": "T2610091647498994259007",
        "utr": "561219197980",
        "transaction_date": "2026-10-09",
        "transaction_time": "16:47",
        "payment_app": "PhonePe",
        "payment_status_text": "Payment Successful",
        "payment_perspective": "payer",
        "field_confidence": {"amount": "high", "utr": "high"},
        "uncertain_fields": [],
        "warnings": [],
    }

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(mock_payload)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.analysis.deepseek_vision.get_deepseek_async_client", return_value=mock_client):
        img_bytes = _make_dummy_image()
        result = await analyze_payment_screenshot_deepseek_async(img_bytes)

        assert result is not None
        assert result.amount == 10.0
        assert result.utr == "561219197980"
        assert result.payment_app == "PhonePe"


@pytest.mark.asyncio
async def test_deepseek_bhim_sample_extraction():
    """Simulates extraction on reference sample BHIM: ₹1, transaction ID 170359197682."""
    mock_payload = {
        "amount": 1.0,
        "raw_amount_text": "₹1.00",
        "currency": "INR",
        "receiver_name": "Kiran Dairy",
        "receiver_upi_id": None,
        "transaction_id": "170359197682",
        "utr": "170359197682",
        "transaction_date": "2026-10-08",
        "transaction_time": "11:20",
        "payment_app": "BHIM",
        "payment_status_text": "Completed",
        "payment_perspective": "payer",
        "field_confidence": {"amount": "high", "transaction_id": "high"},
        "uncertain_fields": [],
        "warnings": [],
    }

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(mock_payload)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.analysis.deepseek_vision.get_deepseek_async_client", return_value=mock_client):
        img_bytes = _make_dummy_image()
        result = await analyze_payment_screenshot_deepseek_async(img_bytes)

        assert result is not None
        assert result.amount == 1.0
        assert result.utr == "170359197682"
        assert result.payment_app == "BHIM"


@pytest.mark.asyncio
async def test_fallback_to_local_ocr_when_deepseek_fails(monkeypatch):
    """If DeepSeek throws an exception or timeout and Gemini is not available, the pipeline falls back to local OCR."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API Gateway Timeout"))

    with patch("app.analysis.deepseek_vision.get_deepseek_async_client", return_value=mock_client), \
         patch("app.analysis.payment_extractor.get_gemini_client", return_value=None):
        img_bytes = _make_dummy_image()
        result = await extract_payment_screenshot_details_async(img_bytes)

        # Fallback must succeed and mark engine as local_ocr
        assert result is not None
        assert result.get("engine_used") == "local_ocr"


def test_api_cross_verify_with_deepseek(client, auth_headers, test_user, db_session):
    """End-to-end integration test of /api/payments/cross-verify with DeepSeek."""
    order = Order(
        seller_id=test_user.id,
        expected_amount=10.00,
        customer_label="Ananya Sharma",
        status="pending",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    code = create_order_referral_code(db_session, order.id, test_user.id)

    mock_extracted = DeepSeekPaymentExtraction(
        amount=10.0,
        raw_amount_text="₹10.00",
        currency="INR",
        receiver_name="Artisan Boutique",
        receiver_upi_id="artisan@upi",
        transaction_id="561219197980",
        utr="561219197980",
        transaction_date="2026-10-09",
        payment_app="PhonePe",
        payment_status_text="Payment Successful",
        payment_perspective="payer",
        field_confidence={"amount": "high"},
        uncertain_fields=[],
        warnings=[],
    )

    with patch("app.analysis.payment_extractor.get_deepseek_async_client") as mock_get_client, \
         patch("app.analysis.payment_extractor.analyze_payment_screenshot_deepseek_async", return_value=mock_extracted):
        mock_get_client.return_value = MagicMock()

        img_bytes = _make_dummy_image()
        response = client.post(
            "/api/payments/cross-verify",
            data={"order_referral_code": code.code},
            files={"screenshot": ("phonepe_proof.jpg", img_bytes, "image/jpeg")},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["risk"]["verdict"] in ("genuine", "careful")
        assert data["risk"]["score"] <= 35
        assert data["extracted"]["amount"] == 10.0
        assert data["extracted"]["engine_used"] == "deepseek-v4.1-flash"
        assert "Risk estimate only" in data["risk"]["disclaimer"]
