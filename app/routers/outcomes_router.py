"""Buyer order outcomes, private evidence, and seller issue resolution."""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import (
    AuditEvent,
    Order,
    OrderOutcome,
    OrderOutcomeEvent,
    OrderOutcomeEvidence,
    PaymentSubmission,
    User,
)
from app.outcome_utils import (
    buyer_access_fingerprint,
    delete_private_evidence,
    load_private_evidence,
    new_buyer_access_code,
    save_private_evidence,
)
from app.schemas import (
    BuyerOrderLookup,
    BuyerOrderOut,
    BuyerOutcomeEventOut,
    BuyerResolutionDecision,
    OrderOutcomeOut,
    SellerOrderOutcomeOut,
    SellerResolutionOffer,
)

router = APIRouter(tags=["order outcomes"])
_PROBLEM_REASONS = {"not_received", "wrong_item", "damaged_item", "missing_item", "not_as_described"}
_PHOTO_MIME = {"image/jpeg", "image/png", "image/webp"}


def _event_out(event: OrderOutcomeEvent) -> BuyerOutcomeEventOut:
    return BuyerOutcomeEventOut(
        event_type=event.event_type,
        actor_type=event.actor_type,
        message=event.message,
        resolution_type=event.resolution_type,
        created_at=event.created_at,
        evidence_ids=[row.id for row in event.evidence],
    )


def _outcome_out(outcome: OrderOutcome) -> OrderOutcomeOut:
    return OrderOutcomeOut(
        id=outcome.id,
        order_id=outcome.order_id,
        outcome=outcome.outcome,
        reason=outcome.reason,
        description=outcome.description,
        status=outcome.status,
        reported_at=outcome.reported_at,
        buyer_received_at=outcome.buyer_received_at,
        response_deadline=outcome.response_deadline,
        seller_resolution_type=outcome.seller_resolution_type,
        seller_response=outcome.seller_response,
        seller_responded_at=outcome.seller_responded_at,
        resolved_at=outcome.resolved_at,
        events=[_event_out(event) for event in outcome.events],
    )


def _append_event(
    db: Session,
    outcome: OrderOutcome,
    actor_type: str,
    actor_id: int,
    event_type: str,
    message: Optional[str] = None,
    resolution_type: Optional[str] = None,
    evidence: Optional[tuple[str, str, int]] = None,
) -> OrderOutcomeEvent:
    event = OrderOutcomeEvent(
        outcome_id=outcome.id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        resolution_type=resolution_type,
        message=message,
    )
    db.add(event)
    db.flush()
    if evidence:
        storage_key, mime_type, size_bytes = evidence
        db.add(OrderOutcomeEvidence(
            event_id=event.id,
            storage_key=storage_key,
            mime_type=mime_type,
            file_size_bytes=size_bytes,
        ))
    return event


def _order_from_buyer_reference(access_code: Optional[str], db: Session) -> Order:
    """Resolve the private buyer reference (e.g. TXN-PCFY-4A5K) or full buyer link."""
    code = (access_code or "").strip()
    if "#claim=" in code:
        code = code.split("#claim=")[-1].split("&")[0].strip()
    elif "?claim=" in code:
        code = code.split("?claim=")[-1].split("&")[0].strip()
    elif "?ref=" in code:
        code = code.split("?ref=")[-1].split("&")[0].strip()
    elif "#ref=" in code:
        code = code.split("#ref=")[-1].split("&")[0].strip()
    elif "#" in code and len(code.split("#")[-1].strip()) >= 8:
        code = code.split("#")[-1].strip()

    if not 8 <= len(code) <= 100:
        raise HTTPException(status_code=404, detail="Order reference not found.")

    fingerprint = buyer_access_fingerprint(code)
    order = db.query(Order).filter(Order.buyer_access_hmac == fingerprint).first()
    if not order and code.upper() != code:
        order = db.query(Order).filter(Order.buyer_access_hmac == buyer_access_fingerprint(code.upper())).first()

    if not order and code.upper().startswith("TXN-"):
        submission = (
            db.query(PaymentSubmission)
            .filter(PaymentSubmission.verification_tx_id == code.upper())
            .first()
        )
        if submission and submission.order:
            order = submission.order
            if not order.buyer_access_hmac:
                order.buyer_access_hmac = buyer_access_fingerprint(code.upper())
                db.commit()

    if not order:
        raise HTTPException(status_code=404, detail="Order reference not found.")
    return order


@router.post("/api/buyer/order/lookup", response_model=BuyerOrderOut)
def lookup_buyer_order(
    payload: BuyerOrderLookup,
    response: Response,
    db: Session = Depends(get_db),
):
    order = _order_from_buyer_reference(payload.access_code, db)
    response.headers["Cache-Control"] = "private, no-store"
    return _buyer_order(order)


def _buyer_order(order: Order) -> BuyerOrderOut:
    return BuyerOrderOut(
        id=order.id,
        referral_code=order.referral_code.code if order.referral_code else None,
        item=order.customer_label or (order.product.name if order.product else None),
        quantity=order.quantity,
        expected_amount=order.expected_amount,
        seller_name=(
            order.seller.profile.business_name or order.seller.profile.contact_name
            if order.seller.profile else None
        ),
        status=order.status,
        can_submit_outcome=order.status == "seller_confirmed",
        outcome=_outcome_out(order.outcome) if order.outcome else None,
    )


@router.post("/api/buyer/order/outcome", response_model=OrderOutcomeOut, status_code=201)
def submit_outcome(
    outcome_type: str = Form(..., alias="outcome"),
    confirmed_received: bool = Form(False),
    confirmed_not_received: bool = Form(False),
    reason: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    access_code: Optional[str] = Header(None, alias="X-Buyer-Access-Code"),
    db: Session = Depends(get_db),
):
    order = _order_from_buyer_reference(access_code, db)
    if order.status != "seller_confirmed":
        raise HTTPException(status_code=409, detail="You can update the outcome after the seller confirms bank credit.")
    if outcome_type not in {"received_as_described", "report_problem"}:
        raise HTTPException(status_code=422, detail="Choose a valid order outcome.")
    is_problem = outcome_type == "report_problem"
    cleaned_reason = (reason or "").strip().lower()
    cleaned_description = (description or "").strip()
    not_received_report = is_problem and cleaned_reason == "not_received"
    if not_received_report and not confirmed_not_received:
        raise HTTPException(status_code=409, detail="Confirm that this order has not arrived before reporting it.")
    if not_received_report and confirmed_received:
        raise HTTPException(status_code=409, detail="Choose either 'Order not received' or confirm that you received the item.")
    if not confirmed_received and not not_received_report:
        raise HTTPException(status_code=409, detail="Confirm receipt before submitting this outcome, or choose 'Order not received'.")
    if confirmed_not_received and not not_received_report:
        raise HTTPException(status_code=409, detail="The 'not received' confirmation only applies to an 'Order not received' report.")

    if is_problem:
        if cleaned_reason not in _PROBLEM_REASONS:
            raise HTTPException(status_code=422, detail="Choose a valid problem reason.")
        if not cleaned_description or len(cleaned_description) > 2000:
            raise HTTPException(status_code=422, detail="Add a problem description of up to 2,000 characters.")
    if photo and photo.filename and photo.content_type not in _PHOTO_MIME:
        raise HTTPException(status_code=415, detail="Photo must be JPEG, PNG, or WebP.")

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    current = (
        db.query(OrderOutcome)
        .filter(OrderOutcome.order_id == order.id)
        .with_for_update()
        .first()
    )
    if current:
        if current.outcome == "problem" or not is_problem:
            raise HTTPException(status_code=409, detail="An outcome has already been recorded for this order.")
        if cleaned_reason == "not_received":
            raise HTTPException(status_code=409, detail="This order already has a receipt confirmation.")
        changed = (
            db.query(OrderOutcome)
            .filter(OrderOutcome.id == current.id, OrderOutcome.outcome == "received")
            .update({
                OrderOutcome.outcome: "problem",
                OrderOutcome.reason: cleaned_reason,
                OrderOutcome.description: cleaned_description,
                OrderOutcome.status: "awaiting_seller",
                OrderOutcome.reported_at: now,
                OrderOutcome.problem_reported_at: now,
                OrderOutcome.response_deadline: now + datetime.timedelta(hours=settings.order_issue_response_hours),
            }, synchronize_session=False)
        )
        if changed != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="An issue report already exists for this order.")
        db.expire(current)
        current = db.query(OrderOutcome).filter(OrderOutcome.id == current.id).one()
    saved = save_private_evidence(photo)
    if current:
        # Keep the earlier positive event/photo while adding exactly one later problem report.
        event_type = "problem_reported"
    else:
        current = OrderOutcome(
            order_id=order.id,
            buyer_id=order.buyer_id,
            outcome="problem" if is_problem else "received",
            reason=cleaned_reason if is_problem else None,
            description=cleaned_description if is_problem else None,
            status="awaiting_seller" if is_problem else "received",
            reported_at=now,
            buyer_received_at=now if confirmed_received else None,
            problem_reported_at=now if is_problem else None,
            response_deadline=(
                now + datetime.timedelta(hours=settings.order_issue_response_hours) if is_problem else None
            ),
        )
        db.add(current)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="An outcome has already been recorded for this order.")
        event_type = "problem_reported" if is_problem else "received_as_described"

    try:
        _append_event(
            # Anonymous buyer actions are authenticated by the private order reference.
            db, current, "buyer", order.buyer_id or 0, event_type,
            message=cleaned_description if is_problem else None,
            evidence=saved,
        )
        if is_problem:
            deadline_text = (
                current.response_deadline.strftime("%Y-%m-%d %H:%M UTC")
                if current.response_deadline
                else "the configured deadline"
            )
            db.add(AuditEvent(
                user_id=order.seller_id,
                event_type="buyer_problem_reported",
                entity_type="order",
                entity_id=order.id,
                detail=f"A buyer reported an order issue. Respond by {deadline_text}.",
            ))
        db.commit()
    except IntegrityError:
        db.rollback()
        if saved:
            delete_private_evidence(saved[0])
        raise HTTPException(status_code=409, detail="An outcome has already been recorded for this order.")
    except Exception:
        db.rollback()
        if saved:
            delete_private_evidence(saved[0])
        raise
    db.refresh(current)
    return _outcome_out(current)


@router.post("/api/buyer/order/outcome/resolution", response_model=OrderOutcomeOut)
def decide_resolution(
    payload: BuyerResolutionDecision,
    access_code: Optional[str] = Header(None, alias="X-Buyer-Access-Code"),
    db: Session = Depends(get_db),
):
    order = _order_from_buyer_reference(access_code, db)
    outcome = (
        db.query(OrderOutcome)
        .filter(OrderOutcome.order_id == order.id, OrderOutcome.outcome == "problem")
        .with_for_update()
        .first()
    )
    if not outcome:
        raise HTTPException(status_code=404, detail="Problem report not found.")
    if outcome.status != "resolution_offered":
        raise HTTPException(status_code=409, detail="The seller has not offered a resolution to confirm.")

    if payload.resolved:
        outcome.status = "resolved"
        outcome.resolved_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        event_type = "buyer_confirmed_resolved"
    else:
        outcome.status = "awaiting_seller"
        outcome.seller_resolution_type = None
        outcome.seller_response = None
        outcome.seller_responded_at = None
        outcome.resolved_at = None
        event_type = "buyer_says_unresolved"
    _append_event(
        db, outcome, "buyer", order.buyer_id or 0, event_type,
        message=(payload.message or "").strip() or None,
    )
    db.commit()
    db.refresh(outcome)
    return _outcome_out(outcome)


@router.get("/api/seller/order-outcomes", response_model=list[SellerOrderOutcomeOut])
def seller_outcomes(
    seller: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(OrderOutcome)
        .join(Order, Order.id == OrderOutcome.order_id)
        .filter(Order.seller_id == seller.id)
        .order_by(OrderOutcome.reported_at.desc())
        .all()
    )
    result = []
    for outcome in rows:
        base = _outcome_out(outcome).model_dump()
        order = outcome.order
        result.append(SellerOrderOutcomeOut(
            **base,
            referral_code=order.referral_code.code if order.referral_code else None,
            item=order.customer_label or (order.product.name if order.product else None),
            expected_amount=order.expected_amount,
            customer_label=order.customer_label,
        ))
    return result


@router.post("/api/orders/{order_id}/outcome/offer", response_model=OrderOutcomeOut)
def offer_resolution(
    order_id: int,
    payload: SellerResolutionOffer,
    seller: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    outcome = (
        db.query(OrderOutcome)
        .join(Order, Order.id == OrderOutcome.order_id)
        .filter(Order.id == order_id, Order.seller_id == seller.id, OrderOutcome.outcome == "problem")
        .first()
    )
    if not outcome:
        raise HTTPException(status_code=404, detail="Problem report not found.")
    if outcome.status == "resolved":
        raise HTTPException(status_code=409, detail="The buyer has already confirmed this issue resolved.")

    message = (payload.message or "").strip() or None
    outcome.seller_resolution_type = payload.resolution_type
    outcome.seller_response = message
    outcome.seller_responded_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    outcome.status = "resolution_offered"
    _append_event(
        db, outcome, "seller", seller.id, "seller_resolution_offered",
        message=message, resolution_type=payload.resolution_type,
    )
    db.commit()
    db.refresh(outcome)
    return _outcome_out(outcome)


def _private_image_response(evidence: Optional[OrderOutcomeEvidence]) -> Response:
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence photo not found.")
    data = load_private_evidence(evidence.storage_key)
    return Response(
        content=data,
        media_type=evidence.mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/api/buyer/order/evidence/{evidence_id}")
def buyer_evidence(
    evidence_id: int,
    access_code: Optional[str] = Header(None, alias="X-Buyer-Access-Code"),
    db: Session = Depends(get_db),
):
    order = _order_from_buyer_reference(access_code, db)
    evidence = (
        db.query(OrderOutcomeEvidence)
        .join(OrderOutcomeEvent, OrderOutcomeEvent.id == OrderOutcomeEvidence.event_id)
        .join(OrderOutcome, OrderOutcome.id == OrderOutcomeEvent.outcome_id)
        .join(Order, Order.id == OrderOutcome.order_id)
        .filter(
            Order.id == order.id,
            OrderOutcomeEvidence.id == evidence_id,
        )
        .first()
    )
    return _private_image_response(evidence)


@router.get("/api/seller/order-outcomes/{outcome_id}/evidence/{evidence_id}")
def seller_evidence(
    outcome_id: int,
    evidence_id: int,
    seller: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    evidence = (
        db.query(OrderOutcomeEvidence)
        .join(OrderOutcomeEvent, OrderOutcomeEvent.id == OrderOutcomeEvidence.event_id)
        .join(OrderOutcome, OrderOutcome.id == OrderOutcomeEvent.outcome_id)
        .join(Order, Order.id == OrderOutcome.order_id)
        .filter(
            OrderOutcome.id == outcome_id,
            Order.seller_id == seller.id,
            OrderOutcomeEvidence.id == evidence_id,
        )
        .first()
    )
    return _private_image_response(evidence)
