"""
Unit tests for forensics, duplicate detection, and payment cross-verification.
"""
import io
import json

from PIL import Image

from app.analysis.duplicate_detection import (
    _hmac_fingerprint,
    check_duplicate_reference,
    record_payment_reference,
)
from app.analysis.forensics import (
    analyze_image,
    compute_phash,
    compute_sha256,
    phash_distance,
)
from app.analysis.ocr_check import _extract_from_text
from app.models import Order, PaymentSubmission
from app.referral_codes import create_order_referral_code


def _create_synthetic_test_image(color=(70, 130, 180), size=(120, 120)) -> bytes:
    """Create a minimal RGB JPEG image in memory."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_sha256_computation():
    data = b"TrustCheck Test Image Payload"
    digest = compute_sha256(data)
    assert len(digest) == 64
    assert digest == compute_sha256(data)


def test_phash_and_distance():
    img1 = _create_synthetic_test_image(color=(100, 100, 100))
    img2 = _create_synthetic_test_image(color=(105, 105, 105))
    img3 = _create_synthetic_test_image(color=(250, 20, 20))

    h1 = compute_phash(img1)
    h2 = compute_phash(img2)
    h3 = compute_phash(img3)

    assert h1 is not None
    assert h2 is not None
    assert h3 is not None
    # Identical/very similar images should have distance near 0
    dist_similar = phash_distance(h1, h2)
    assert dist_similar is not None
    assert dist_similar <= 5

    # Dissimilar images should have larger distance
    dist_diff = phash_distance(h1, h3)
    assert dist_diff is not None


def test_image_forensics():
    img_bytes = _create_synthetic_test_image()
    forensics = analyze_image(img_bytes)

    assert forensics["sha256"] is not None
    assert forensics["phash"] is not None
    assert forensics["image_width"] == 120
    assert forensics["image_height"] == 120
    assert "ela_score" in forensics


def test_exif_editing_warning_cannot_be_genuine():
    from app.routers.payments_router import _compute_risk

    order = Order(id=1, expected_amount=11.0, expected_payee_name="Johan Melvin")
    result = _compute_risk(
        order=order,
        extracted={"amount": 11.0, "payee_name": "JOHAN MELVIN", "viewpoint": "payer"},
        submitted_tx_id=None,
        duplicate_ref=None,
        duplicate_img=None,
        forensics={"findings": [{
            "check": "exif_software",
            "level": "warning",
            "detail": "Image was processed by editing software (Snapseed).",
        }]},
    )

    assert result.score == 20
    assert result.verdict == "careful"


def test_hmac_fingerprint_normalization():
    # Different whitespace / case should yield the same HMAC fingerprint
    fp1 = _hmac_fingerprint("upi-ref-123456789")
    fp2 = _hmac_fingerprint("  UPI-REF-123456789 ")
    assert fp1 == fp2
    assert len(fp1) == 64


def test_duplicate_reference_detection(db_session, test_user):
    order = Order(seller_id=test_user.id, expected_amount=400.0, status="pending")
    db_session.add(order)
    db_session.commit()

    sub = PaymentSubmission(order_id=order.id, seller_id=test_user.id, risk_score=10)
    db_session.add(sub)
    db_session.commit()

    tx_id = "TXN_UPI_9876543210"
    # First time: record reference
    record_payment_reference(db_session, test_user.id, order.id, sub.id, tx_id)
    db_session.commit()

    # Second time: checking the same reference should flag duplicate
    dup = check_duplicate_reference(db_session, tx_id)
    assert dup is not None
    assert dup["duplicate_found"] is True
    assert dup["first_seen_order_id"] == order.id

    # An unknown reference should NOT be flagged
    no_dup = check_duplicate_reference(db_session, "BRAND_NEW_TX_9999")
    assert no_dup is None


def test_public_buyer_verify_with_order_code(client, test_user, db_session):
    """Buyers can submit payment verification without logging in using order code."""
    order = Order(
        seller_id=test_user.id,
        expected_amount=950.0,
        expected_upi_id=test_user.profile.upi_id,
        status="pending",
    )
    db_session.add(order)
    db_session.commit()
    orc = create_order_referral_code(db_session, order.id, test_user.id)

    # Public POST without Authorization headers
    res = client.post(
        "/api/payments/cross-verify",
        data={
            "order_referral_code": orc.code,
            "submitted_tx_id": "UPI_REF_PUBLIC_12345",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["order_referral_code"] == orc.code
    assert "risk" in data
    assert data["expected_amount"] == 950.0
    assert "verification_tx_id" in data and data["verification_tx_id"].startswith("TXN-")


def test_public_buyer_verify_with_order_id_only(client, db_session, test_user):
    """Buyers can verify order using only the Order ID without screenshot or referral code."""
    order = Order(
        seller_id=test_user.id,
        expected_amount=1500.0,
        expected_upi_id="crafts@upi",
        expected_payee_name="Artisan Store",
        customer_label="Priya K",
        status="pending",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    orc = create_order_referral_code(db_session, order.id, test_user.id)

    # Public buyer POST using only numeric order ID
    res = client.post(
        "/api/payments/cross-verify",
        data={"order_referral_code": str(order.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["order_id"] == order.id
    assert data["expected_amount"] == 1500.0
    assert data["expected_payee_name"] == "Artisan Store"
    assert data["expected_upi_id"] == "crafts@upi"
    assert "verification_tx_id" in data and data["verification_tx_id"].startswith("TXN-")
    assert data["risk"]["verdict"] == "careful"
    assert "not proof of payment" in data["risk"]["disclaimer"].lower()

    # Also supports prefixed "#123"
    res2 = client.post(
        "/api/payments/cross-verify",
        data={"order_referral_code": f"#{order.id}"},
    )
    assert res2.status_code == 200
    assert res2.json()["order_id"] == order.id


def test_public_buyer_verify_with_seller_code(client, test_user):
    """Buyers can also submit payment verification using the seller's permanent code."""
    seller_code = test_user.seller_referral_code.code

    # Public POST without Authorization headers using SL-XXXX-XXXX
    res = client.post(
        "/api/payments/cross-verify",
        data={
            "order_referral_code": seller_code,
            "submitted_tx_id": "UPI_REF_SELLER_CODE_999",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "risk" in data
    assert data["submitted_tx_id"] == "UPI_REF_SELLER_CODE_999"
    assert "verification_tx_id" in data and data["verification_tx_id"].startswith("TXN-")


def test_analysis_details_are_saved_for_seller_dashboard(
    client, test_user, db_session, auth_headers, monkeypatch
):
    """Seller history retains extracted, forensic, comparison, and duplicate analysis."""
    from app.routers import payments_router

    order = Order(
        seller_id=test_user.id,
        expected_amount=100.0,
        expected_payee_name="Artisan Store",
        expected_upi_id="artisan@upi",
        status="pending",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    order_code = create_order_referral_code(db_session, order.id, test_user.id)

    async def fake_extract(_image_bytes, **_kwargs):
        return {
            "amount": 80.0,
            "currency": "INR",
            "tx_id": "UPI-REF-12345",
            "utr": "UPI-REF-12345",
            "payee_name": "Different Payee",
            "payee_upi_id": "other@upi",
            "date_str": "10 Oct 2026",
            "time_str": "10:30 AM",
            "app_indicator": "test-upi",
            "status_text": "Payment successful",
            "viewpoint": "payer",
            "ocr_confidence": 0.92,
            "engine_used": "test-engine",
            "field_confidence": {"amount": 0.92},
            "uncertain_fields": [],
            "warnings": ["Test extraction warning"],
        }

    def fake_forensics(_image_bytes):
        return {
            "sha256": "a" * 64,
            "phash": "0123456789abcdef",
            "file_size_bytes": 4096,
            "image_width": 320,
            "image_height": 640,
            "has_exif": True,
            "exif_safe_fields": {"Software": "Test Editor", "ImageWidth": "320"},
            "ela_score": 9.5,
            "findings": [{"check": "exif_software", "level": "warning", "detail": "Edited software detected."}],
            "observations": ["Synthetic test image."],
            "disclaimer": "Forensics are supporting observations only.",
        }

    monkeypatch.setattr(payments_router, "extract_payment_screenshot_details_async", fake_extract)
    monkeypatch.setattr(payments_router, "analyze_image", fake_forensics)
    screenshot = _create_synthetic_test_image()

    first = client.post(
        "/api/payments/cross-verify",
        data={"order_referral_code": order_code.code},
        files={"screenshot": ("receipt.jpg", screenshot, "image/jpeg")},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/payments/cross-verify",
        data={"order_referral_code": order_code.code},
        files={"screenshot": ("receipt.jpg", screenshot, "image/jpeg")},
    )
    assert second.status_code == 200

    history = client.get("/api/payments/history", headers=auth_headers)
    assert history.status_code == 200
    latest = next(item for item in history.json() if item["submission_id"] == second.json()["submission_id"])

    assert latest["extracted_fields"]["amount"] == 80.0
    assert latest["forensics"]["exif_safe_fields"]["Software"] == "Test Editor"
    assert latest["forensics"]["ela_score"] == 9.5
    assert latest["comparison"]["amount_match"] is False
    assert latest["comparison"]["payee_name_match"] is False
    assert "upi_match" not in latest["comparison"]
    assert latest["extracted_fields"]["payee_upi_id"] == "other@upi"
    assert latest["duplicates"]["transaction_reference"]["duplicate_found"] is True
    assert latest["duplicates"]["screenshot"]["duplicate_found"] is True
    assert latest["disclaimer"] == "Risk estimate only — not proof of payment."


def _create_saved_verification(db_session, test_user, verification_tx_id="TXN-ABCD-EFGH"):
    order = Order(
        seller_id=test_user.id,
        expected_amount=100.0,
        expected_payee_name="Artisan Store",
        status="pending",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    submission = PaymentSubmission(
        order_id=order.id,
        seller_id=test_user.id,
        verification_tx_id=verification_tx_id,
        screenshot_sha256="a" * 64,
        screenshot_phash="0123456789abcdef",
        screenshot_file_size=4096,
        extracted_amount=80.0,
        extracted_tx_id="UPI-REF-12345",
        extracted_payee_name="Different Payee",
        risk_score=60,
        risk_verdict="suspicious",
        risk_reasons_json=json.dumps([{"level": "error", "text": "Amount mismatch."}]),
        extracted_json=json.dumps({
            "amount": 80.0,
            "tx_id": "UPI-REF-12345",
            "utr": "UPI-REF-12345",
            "payee_name": "Different Payee",
            "viewpoint": "payer",
        }),
        forensics_json=json.dumps({
            "image_width": 320,
            "image_height": 640,
            "file_size_bytes": 4096,
            "has_exif": True,
            "exif_safe_fields": {"Software": "Test Editor"},
            "ela_score": 9.5,
            "findings": [{"check": "exif_software", "level": "warning", "detail": "Edited software detected."}],
        }),
        duplicate_json=json.dumps({
            "transaction_reference": {"duplicate_found": False},
            "screenshot": {"duplicate_found": True, "message": "This screenshot was seen before."},
        }),
        comparison_json=json.dumps({
            "expected_amount": 100.0,
            "expected_payee_name": "Artisan Store",
            "amount_match": False,
            "payee_name_match": False,
        }),
    )
    db_session.add(submission)
    db_session.commit()
    return order, submission


def test_seller_verification_reference_returns_saved_analysis_without_new_submission(
    client, test_user, db_session, auth_headers
):
    _, submission = _create_saved_verification(db_session, test_user)

    response = client.post(
        "/api/payments/cross-verify",
        data={"order_referral_code": submission.verification_tx_id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["submission_id"] == submission.id
    assert data["extracted_fields"]["amount"] == 80.0
    assert data["comparison"]["amount_match"] is False
    assert data["forensics"]["exif_safe_fields"]["Software"] == "Test Editor"
    assert data["duplicates"]["screenshot"]["duplicate_found"] is True
    assert data["risk"]["verdict"] == "suspicious"
    assert db_session.query(PaymentSubmission).count() == 1


def test_verification_reference_requires_seller_login(client, test_user, db_session):
    _, submission = _create_saved_verification(db_session, test_user)

    response = client.post(
        "/api/payments/cross-verify",
        data={"order_referral_code": submission.verification_tx_id},
    )

    assert response.status_code == 401


def test_verification_reference_is_scoped_to_owning_seller(client, test_user, db_session):
    from app.auth import create_access_token
    from app.models import User

    _, submission = _create_saved_verification(db_session, test_user)
    other_seller = User(
        email="other_seller@trustcheck.com",
        hashed_password="unused",
        is_active=True,
    )
    db_session.add(other_seller)
    db_session.commit()
    other_headers = {"Authorization": f"Bearer {create_access_token(other_seller.id)}"}

    response = client.post(
        "/api/payments/cross-verify",
        data={"order_referral_code": submission.verification_tx_id},
        headers=other_headers,
    )

    assert response.status_code == 404


def test_seller_history_corrects_old_exif_genuine_verdict(client, test_user, db_session, auth_headers):
    """Older saved records with an EXIF warning are shown as careful, not genuine."""
    order = Order(seller_id=test_user.id, expected_amount=11.0, status="pending")
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    submission = PaymentSubmission(
        order_id=order.id,
        seller_id=test_user.id,
        risk_score=10,
        risk_verdict="genuine",
        risk_reasons_json='[{"level":"warning","text":"[Forensics] Editing software detected."}]',
        comparison_json='{"expected_amount":11.0,"upi_match":false}',
        forensics_json=(
            '{"findings":[{"check":"exif_software","level":"warning",'
            '"detail":"Image was processed by Snapseed."}]}'
        ),
    )
    db_session.add(submission)
    db_session.commit()

    response = client.get("/api/payments/history", headers=auth_headers)

    assert response.status_code == 200
    record = next(item for item in response.json() if item["submission_id"] == submission.id)
    assert record["risk_score"] == 20
    assert record["risk_verdict"] == "careful"
    assert "upi_match" not in record["comparison"]
    db_session.refresh(submission)
    assert submission.risk_verdict == "careful"
    assert "upi_match" not in submission.comparison_json


def test_extract_payment_fields_patterns():
    # PhonePe format
    phonepe_text = (
        "Paid to\n"
        "Artisan Handicrafts\n"
        "1,250\n"
        "Payment of 1,250 was successful\n"
        "09 Oct 2026\n"
        "Banking Name: ARTISAN HANDICRAFTS\n"
        "UTR: 628276953170\n"
    )
    res_pp = _extract_from_text(phonepe_text, expected_amount=1250.0, expected_payee_name="Artisan Handicrafts")
    assert res_pp["amount"] == 1250.0
    assert "ARTISAN HANDICRAFTS" in res_pp["payee_name"]
    assert res_pp["utr"] == "628276953170"

    # Google Pay format with rupee OCR symbol and layout
    gpay_text = (
        "Aarav Sharma\n"
        "aarav@okaxis\n"
        "0500.00\n"
        "Completed\n"
        "09 Oct 2026, 06:30 PM\n"
        "UPI transaction ID: 628276953170\n"
    )
    res_gpay = _extract_from_text(gpay_text, expected_amount=500.0, expected_payee_name="Aarav Sharma")
    assert res_gpay["amount"] == 500.0
    assert res_gpay["payee_name"] == "Aarav Sharma"
    assert res_gpay["payee_upi_id"] == "aarav@okaxis"
    assert res_gpay["tx_id"] == "628276953170"

    # Paytm format
    paytm_text = (
        "₹ 950.00\n"
        "Payment Successful\n"
        "Paid to Craft Studio\n"
        "UPI Ref: 123456789012\n"
    )
    res_paytm = _extract_from_text(paytm_text, expected_amount=950.0, expected_payee_name="Craft Studio")
    assert res_paytm["amount"] == 950.0
    assert res_paytm["payee_name"] == "Craft Studio"

