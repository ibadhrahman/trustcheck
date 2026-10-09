"""
Referral-code generation and validation.
Codes are unpredictable, human-readable, and unique.
"""
from __future__ import annotations

import secrets
import string

from sqlalchemy.orm import Session

from app.models import OrderReferralCode, SellerReferralCode

_ALPHABET = string.ascii_uppercase + string.digits
_ALPHABET = _ALPHABET.replace("O", "").replace("0", "").replace("I", "").replace("1", "")


def _random_segment(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def generate_seller_code() -> str:
    """Generate a seller-level referral code like SL-XXXX-XXXX."""
    return f"SL-{_random_segment(4)}-{_random_segment(4)}"


def generate_order_code() -> str:
    """Generate an order-level referral code like TC-XXXXXXXX."""
    return f"TC-{_random_segment(8)}"


def create_seller_referral_code(db: Session, seller_id: int) -> SellerReferralCode:
    """Create (or return existing) seller referral code."""
    existing = db.query(SellerReferralCode).filter(
        SellerReferralCode.seller_id == seller_id
    ).first()
    if existing:
        return existing

    for _ in range(10):
        code = generate_seller_code()
        if not db.query(SellerReferralCode).filter(SellerReferralCode.code == code).first():
            break
    else:
        raise RuntimeError("Failed to generate unique seller referral code.")

    src = SellerReferralCode(seller_id=seller_id, code=code)
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


def create_order_referral_code(
    db: Session, order_id: int, seller_id: int
) -> OrderReferralCode:
    """Create a unique order referral code."""
    for _ in range(10):
        code = generate_order_code()
        if not db.query(OrderReferralCode).filter(OrderReferralCode.code == code).first():
            break
    else:
        raise RuntimeError("Failed to generate unique order referral code.")

    orc = OrderReferralCode(order_id=order_id, seller_id=seller_id, code=code)
    db.add(orc)
    db.commit()
    db.refresh(orc)
    return orc


def resolve_order_referral_code(
    db: Session, code: str
) -> OrderReferralCode | None:
    """Resolve a code to an active OrderReferralCode record, or None."""
    cleaned = code.strip().upper()
    return (
        db.query(OrderReferralCode)
        .filter(OrderReferralCode.code == cleaned, OrderReferralCode.is_active == True)
        .first()
    )


def resolve_seller_referral_code(
    db: Session, code: str
) -> SellerReferralCode | None:
    """Resolve a code to a SellerReferralCode record, or None."""
    cleaned = code.strip().upper()
    return (
        db.query(SellerReferralCode)
        .filter(SellerReferralCode.code == cleaned)
        .first()
    )


def build_shareable_message(code: str, amount: float, upi_id: str | None = None) -> str:
    upi_line = f"\nPay to UPI ID: {upi_id}" if upi_id else ""
    return (
        f"Order reference: {code}\n"
        f"Expected amount: ₹{amount:.2f}"
        f"{upi_line}\n"
        "After making the payment through your usual payment app, "
        "share the transaction reference with the seller."
    )


def generate_verification_tx_id() -> str:
    """Generate a unique verification transaction ID like TXN-XXXX-XXXX."""
    return f"TXN-{_random_segment(4)}-{_random_segment(4)}"


def build_buyer_confirmation_message(
    verification_tx_id: str, order_code: str, amount: float | None = None
) -> str:
    amt_line = f"Amount: ₹{amount:.2f}\n" if amount is not None and amount > 0 else ""
    return (
        f"Hi! I have submitted my payment proof on TrustCheck.\n"
        f"Verification Transaction ID: {verification_tx_id}\n"
        f"Order Ref: {order_code}\n"
        f"{amt_line}"
        f"Please confirm receipt in your bank account."
    )
