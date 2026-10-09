"""
Unit tests for referral code generation, format validation, and message templates.
"""
import re
from app.referral_codes import (
    generate_order_code,
    generate_seller_code,
    build_shareable_message,
    create_order_referral_code,
)
from app.models import Order


def test_seller_code_format():
    for _ in range(20):
        code = generate_seller_code()
        assert re.match(r"^SL-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$", code)
        # Ensure no ambiguous characters
        for char in ("0", "O", "1", "I"):
            assert char not in code


def test_order_code_format():
    for _ in range(20):
        code = generate_order_code()
        assert re.match(r"^TC-[A-HJ-NP-Z2-9]{8}$", code)
        for char in ("0", "O", "1", "I"):
            assert char not in code


def test_build_shareable_message():
    msg = build_shareable_message(
        code="TC-7K9M4Q2X",
        amount=1299.50,
        upi_id="crafts@oksbi",
    )
    assert "TC-7K9M4Q2X" in msg
    assert "₹1299.50" in msg
    assert "crafts@oksbi" in msg
    assert "QR" not in msg  # No QR codes used


def test_create_order_referral_code_uniqueness(db_session, test_user):
    order = Order(
        seller_id=test_user.id,
        expected_amount=500.0,
        status="pending",
    )
    db_session.add(order)
    db_session.commit()

    orc = create_order_referral_code(db_session, order.id, test_user.id)
    assert orc.code.startswith("TC-")
    assert orc.order_id == order.id
    assert orc.seller_id == test_user.id
    assert orc.is_active is True
