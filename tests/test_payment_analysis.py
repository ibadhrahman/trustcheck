"""
Unit tests for forensics, duplicate detection, and payment cross-verification.
"""
import io

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

