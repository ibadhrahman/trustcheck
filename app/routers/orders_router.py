"""
Orders and referral code routes:
  POST /api/orders
  GET  /api/orders
  GET  /api/orders/{order_id}
  GET  /api/orders/referral/{referral_code}
  POST /api/orders/{order_id}/cancel
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import AuditEvent, Order, OrderReferralCode, Product, User
from app.outcome_utils import buyer_access_fingerprint, new_buyer_access_code, seller_has_warning
from app.referral_codes import (
    build_shareable_message,
    create_order_referral_code,
    resolve_order_referral_code,
    resolve_seller_referral_code,
)
from app.schemas import BuyerAccessCodeOut, OrderCreate, OrderOut, SellerWarningOut

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _build_order_out(order: Order, buyer_access_code: str | None = None) -> OrderOut:
    code_str = order.referral_code.code if order.referral_code else None
    shareable = (
        build_shareable_message(
            code_str,
            order.expected_amount,
            order.expected_upi_id,
        )
        if code_str
        else None
    )
    return OrderOut(
        id=order.id,
        product_id=order.product_id,
        quantity=order.quantity,
        expected_amount=order.expected_amount,
        expected_payee_name=order.expected_payee_name,
        expected_upi_id=order.expected_upi_id,
        customer_label=order.customer_label,
        status=order.status,
        last_risk_verdict=order.last_risk_verdict,
        last_risk_score=order.last_risk_score,
        created_at=order.created_at,
        referral_code=code_str,
        shareable_message=shareable,
        buyer_access_code=buyer_access_code,
        outcome_status=order.outcome.status if order.outcome else None,
    )


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Optional product ownership check
    if payload.product_id:
        product = db.query(Product).filter(
            Product.id == payload.product_id, Product.seller_id == current_user.id
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found.")

    # Fall back to seller UPI ID if not specified
    upi_id = payload.expected_upi_id
    if not upi_id and current_user.profile and current_user.profile.upi_id:
        upi_id = current_user.profile.upi_id

    payee_name = payload.expected_payee_name
    if not payee_name and current_user.profile:
        payee_name = current_user.profile.business_name or current_user.profile.contact_name

    order = Order(
        seller_id=current_user.id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        expected_amount=payload.expected_amount,
        expected_payee_name=payee_name,
        expected_upi_id=upi_id,
        customer_label=payload.customer_label,
        private_note=payload.private_note,
        status="pending",
    )
    buyer_access_code = ""
    for _ in range(10):
        candidate_code = new_buyer_access_code()
        candidate_hmac = buyer_access_fingerprint(candidate_code)
        if not db.query(Order).filter(Order.buyer_access_hmac == candidate_hmac).first():
            buyer_access_code = candidate_code
            order.buyer_access_hmac = candidate_hmac
            break
    else:
        raise RuntimeError("Failed to generate unique buyer access code.")
    db.add(order)
    db.flush()

    # Generate order referral code
    create_order_referral_code(db, order.id, current_user.id)

    db.add(AuditEvent(
        user_id=current_user.id,
        event_type="order_created",
        entity_type="order",
        entity_id=order.id,
    ))
    db.commit()
    db.refresh(order)
    return _build_order_out(order, buyer_access_code=buyer_access_code)


@router.get("", response_model=list[OrderOut])
def list_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    orders = (
        db.query(Order)
        .filter(Order.seller_id == current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return [_build_order_out(o) for o in orders]


@router.get("/referral/{referral_code}", response_model=OrderOut)
def get_order_by_referral(
    referral_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Resolve an order referral code.
    ONLY the owning seller can access the full private order details.
    """
    orc = resolve_order_referral_code(db, referral_code)
    if not orc:
        raise HTTPException(status_code=404, detail="Referral code not found or inactive.")

    # Ownership enforcement
    if orc.seller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    order = orc.order
    return _build_order_out(order)


@router.get("/referral/{referral_code}/warning", response_model=SellerWarningOut)
def get_seller_warning(referral_code: str, db: Session = Depends(get_db)):
    """Return only a neutral aggregate warning; never report or buyer details."""
    order_code = resolve_order_referral_code(db, referral_code)
    if order_code:
        seller_id = order_code.seller_id
    else:
        seller_code = resolve_seller_referral_code(db, referral_code)
        if not seller_code:
            return SellerWarningOut(warning=False)
        seller_id = seller_code.seller_id

    warning = seller_has_warning(db, seller_id)
    return SellerWarningOut(
        warning=warning,
        message=(
            "Multiple unresolved order issues have been reported. Review before purchasing."
            if warning else None
        ),
    )


@router.post("/{order_id}/buyer-access-code", response_model=BuyerAccessCodeOut)
def rotate_buyer_access_code(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id, Order.seller_id == current_user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order.outcome and order.outcome.outcome == "problem":
        raise HTTPException(
            status_code=409,
            detail="The buyer reference cannot be rotated after an issue report is filed.",
        )
    access_code = ""
    for _ in range(10):
        candidate_code = new_buyer_access_code()
        candidate_hmac = buyer_access_fingerprint(candidate_code)
        if not db.query(Order).filter(Order.buyer_access_hmac == candidate_hmac).first():
            access_code = candidate_code
            order.buyer_access_hmac = candidate_hmac
            break
    else:
        raise RuntimeError("Failed to generate unique buyer access code.")
    db.add(AuditEvent(
        user_id=current_user.id,
        event_type="buyer_access_code_rotated",
        entity_type="order",
        entity_id=order.id,
        detail="A private buyer order reference was rotated.",
    ))
    db.commit()
    return BuyerAccessCodeOut(access_code=access_code)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id, Order.seller_id == current_user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    return _build_order_out(order)


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id, Order.seller_id == current_user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order.status == "seller_confirmed":
        raise HTTPException(status_code=400, detail="Cannot cancel a confirmed order.")

    order.status = "cancelled"
    # Deactivate referral code
    if order.referral_code:
        order.referral_code.is_active = False

    db.add(AuditEvent(
        user_id=current_user.id,
        event_type="order_cancelled",
        entity_type="order",
        entity_id=order.id,
    ))
    db.commit()
    return {"message": "Order cancelled.", "order_id": order_id, "status": "cancelled"}
