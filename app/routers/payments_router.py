"""
Payment analysis and cross-verification routes:
  POST /api/payments/analyze       — OCR + forensics on a screenshot
  POST /api/payments/cross-verify  — Full verification: referral code + tx ID + optional screenshot
  GET  /api/payments/history       — Seller's verification history
  POST /api/orders/{order_id}/confirm-payment
  POST /api/orders/{order_id}/mark-review
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.analysis.duplicate_detection import (
    check_duplicate_reference,
    check_duplicate_screenshot,
    record_payment_reference,
)
from app.analysis.forensics import analyze_image
from app.analysis.ocr_check import extract_payment_fields, get_ocr_availability
from app.analysis.payment_extractor import extract_payment_screenshot_details_async
from app.auth import get_current_user, get_optional_current_user
from app.config import settings
from app.db import get_db
from app.models import AuditEvent, Order, PaymentSubmission, User
from app.referral_codes import (
    create_order_referral_code,
    generate_verification_tx_id,
    resolve_order_referral_code,
    resolve_seller_referral_code,
)
from app.schemas import CrossVerifyResult, ExtractedPaymentFields, RiskReason, RiskResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


def _validate_screenshot(file: UploadFile) -> bytes:
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Use JPEG, PNG, or WebP.",
        )
    data = file.file.read()
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit.",
        )
    return data


def _compute_risk(
    order: Order,
    extracted: Optional[dict],
    submitted_tx_id: Optional[str],
    duplicate_ref: Optional[dict],
    duplicate_img: Optional[dict],
    forensics: Optional[dict],
) -> RiskResult:
    """
    Build a risk score from all available checks.
    Score 0-100: lower = less risk detected.
    Verdict: genuine | careful | suspicious
    """
    score = 0
    reasons: list[RiskReason] = []

    # --- Amount comparison (Decimal-safe) ---
    if extracted:
        ext_amount = extracted.get("amount")
        if ext_amount is None:
            reasons.append(RiskReason(level="warning", text="Payment amount could not be read from the screenshot. Cannot confirm amount match."))
            score += 15
        else:
            try:
                dec_ext = Decimal(str(ext_amount)).quantize(Decimal("0.01"))
                dec_exp = Decimal(str(order.expected_amount)).quantize(Decimal("0.01"))
                if dec_ext == dec_exp:
                    reasons.append(RiskReason(level="ok", text=f"Extracted amount ₹{ext_amount:.2f} matches expected order amount ₹{order.expected_amount:.2f}."))
                else:
                    reasons.append(RiskReason(level="error", text=f"Amount mismatch: screenshot shows ₹{ext_amount:.2f}, order expects ₹{order.expected_amount:.2f}."))
                    score += 40
            except Exception:
                if abs(ext_amount - order.expected_amount) < 0.01:
                    reasons.append(RiskReason(level="ok", text=f"Extracted amount ₹{ext_amount:.2f} matches expected order amount ₹{order.expected_amount:.2f}."))
                else:
                    reasons.append(RiskReason(level="error", text=f"Amount mismatch: screenshot shows ₹{ext_amount:.2f}, order expects ₹{order.expected_amount:.2f}."))
                    score += 40

        # Payee name check
        ext_name = extracted.get("payee_name")
        exp_name = order.expected_payee_name
        if ext_name and exp_name:
            if ext_name.lower().strip() in exp_name.lower() or exp_name.lower().strip() in ext_name.lower():
                reasons.append(RiskReason(level="ok", text=f"Payee name '{ext_name}' appears consistent with expected '{exp_name}'."))
            else:
                reasons.append(RiskReason(level="warning", text=f"Payee name '{ext_name}' does not clearly match expected '{exp_name}'."))
                score += 20
        elif not ext_name:
            reasons.append(RiskReason(level="warning", text="Payee name could not be extracted from screenshot."))
            score += 5

        # Viewpoint check
        viewpoint = extracted.get("viewpoint", "unknown")
        if viewpoint == "receiver":
            reasons.append(RiskReason(level="warning", text="Screenshot may show an incoming-payment view, not a payment-made confirmation. Please review manually."))
            score += 20
        elif viewpoint == "payer":
            reasons.append(RiskReason(level="ok", text="Screenshot appears to show a payment-made confirmation view."))

        # Submitted tx ID vs extracted tx ID
        ext_tx = extracted.get("tx_id") or extracted.get("utr")
        if submitted_tx_id and ext_tx:
            if submitted_tx_id.strip().upper() == ext_tx.strip().upper():
                reasons.append(RiskReason(level="ok", text="Submitted transaction ID matches the ID extracted from the screenshot."))
            else:
                reasons.append(RiskReason(level="error", text=f"Submitted transaction ID '{submitted_tx_id}' does not match extracted ID '{ext_tx}'."))
                score += 35

        # OCR warnings
        for w in extracted.get("warnings", []):
            reasons.append(RiskReason(level="warning", text=w))
            score += 5

    else:
        # No screenshot — can only check tx reference records
        reasons.append(RiskReason(level="warning", text="No screenshot provided. Analysis is based on the submitted transaction reference only."))
        score += 10

    # --- Duplicate reference check ---
    if duplicate_ref and duplicate_ref.get("duplicate_found"):
        reasons.append(RiskReason(level="error", text=duplicate_ref["message"]))
        score += 40

    # --- Duplicate screenshot check ---
    if duplicate_img and duplicate_img.get("duplicate_found"):
        reasons.append(RiskReason(level="error", text=duplicate_img["message"]))
        score += 30

    # --- Forensics ---
    if forensics:
        for finding in forensics.get("findings", []):
            if finding["level"] == "warning":
                reasons.append(RiskReason(level="warning", text=f"[Forensics] {finding['detail']}"))
                score += 10
            elif finding["level"] == "ok":
                reasons.append(RiskReason(level="ok", text=f"[Forensics] {finding['detail']}"))

    # Cap score
    score = min(score, 100)

    # Verdict
    if score >= 55:
        verdict = "suspicious"
    elif score >= 20:
        verdict = "careful"
    else:
        verdict = "genuine"

    if not reasons:
        reasons.append(RiskReason(level="warning", text="Insufficient information for a complete assessment."))

    return RiskResult(
        score=score,
        verdict=verdict,
        reasons=reasons,
        details={
            "ocr_available": any(get_ocr_availability().values()),
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/api/payments/analyze")
async def analyze_payment(
    file: UploadFile = File(...),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """OCR + forensics on a screenshot, without linking to a specific order."""
    data = _validate_screenshot(file)
    extracted = await extract_payment_screenshot_details_async(data)
    forensics = analyze_image(data)
    return {
        "extracted": extracted,
        "forensics": {
            "sha256": forensics["sha256"],
            "phash": forensics["phash"],
            "findings": forensics["findings"],
            "observations": forensics["observations"],
            "disclaimer": forensics["disclaimer"],
        },
        "ocr_availability": get_ocr_availability(),
    }


@router.post("/api/payments/cross-verify", response_model=CrossVerifyResult)
async def cross_verify_payment(
    order_referral_code: str = Form(...),
    submitted_tx_id: Optional[str] = Form(None),
    screenshot: Optional[UploadFile] = File(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Cross-verification pipeline for sellers OR public buyers:
    1. Resolve referral code (works with either order code TC-XXXXXXXX or permanent seller code SL-XXXX-XXXX)
    2. OCR screenshot if provided
    3. Check duplicates
    4. Compare fields
    5. Build risk result
    6. Save privacy-conscious record
    """
    code_cleaned = order_referral_code.strip().upper()
    order = None

    # 1. Resolve order code (TC-XXXXXXXX)
    orc = resolve_order_referral_code(db, code_cleaned)
    if orc:
        if current_user and orc.seller_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied.")
        order = orc.order
    else:
        # 2. Or resolve master seller code (SL-XXXX-XXXX)
        src = resolve_seller_referral_code(db, code_cleaned)
        if src:
            if current_user and src.seller_id != current_user.id:
                raise HTTPException(status_code=403, detail="Access denied.")
            order = (
                db.query(Order)
                .filter(Order.seller_id == src.seller_id, Order.status.in_(["pending", "needs_review"]))
                .order_by(Order.created_at.desc())
                .first()
            )
            if not order:
                seller = src.seller
                profile = seller.profile
                order = Order(
                    seller_id=src.seller_id,
                    expected_amount=0.0,
                    expected_upi_id=profile.upi_id if profile else None,
                    expected_payee_name=profile.business_name or profile.contact_name if profile else None,
                    customer_label="Buyer Payment via Master Seller Code",
                    private_note=f"Submitted using master seller code {src.code}",
                    status="pending",
                )
                db.add(order)
                db.flush()
                create_order_referral_code(db, order.id, src.seller_id)
        else:
            raise HTTPException(
                status_code=404,
                detail="Referral code not found. Please check your seller code (SL-XXXX-XXXX) or order code (TC-XXXXXXXX).",
            )

    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="This order has been cancelled.")

    # --- 2. OCR + forensics ---
    img_data: Optional[bytes] = None
    extracted: Optional[dict] = None
    forensics_result: Optional[dict] = None
    img_sha256: Optional[str] = None
    img_phash: Optional[str] = None

    if screenshot and screenshot.filename:
        img_data = _validate_screenshot(screenshot)
        extracted = await extract_payment_screenshot_details_async(
            img_data,
            expected_amount=order.expected_amount if order else None,
            expected_payee_name=order.expected_payee_name if order else None,
        )
        forensics_result = analyze_image(img_data)
        img_sha256 = forensics_result.get("sha256")
        img_phash = forensics_result.get("phash")

    # --- 3. Duplicate checks ---
    # Use submitted_tx_id OR extracted tx_id for reference check
    tx_ref_for_check = submitted_tx_id
    if not tx_ref_for_check and extracted:
        tx_ref_for_check = extracted.get("tx_id") or extracted.get("utr")

    duplicate_ref = None
    if tx_ref_for_check:
        duplicate_ref = check_duplicate_reference(db, tx_ref_for_check)

    duplicate_img = None
    if img_sha256 or img_phash:
        duplicate_img = check_duplicate_screenshot(db, sha256=img_sha256, phash=img_phash)

    # --- 4. Risk assessment ---
    risk = _compute_risk(order, extracted, submitted_tx_id, duplicate_ref, duplicate_img, forensics_result)

    # --- 5. Update order status if suspicious ---
    if risk.verdict == "suspicious" and order.status == "pending":
        order.status = "needs_review"

    order.last_risk_verdict = risk.verdict
    order.last_risk_score = risk.score

    # --- 6. Save submission record (privacy-conscious, no raw screenshots) ---
    ext_amount = extracted.get("amount") if extracted else None
    ext_tx_id = extracted.get("tx_id") if extracted else None
    ext_date = extracted.get("date_str") if extracted else None
    ext_payee = extracted.get("payee_name") if extracted else None
    viewpoint = extracted.get("viewpoint", "unknown") if extracted else None

    seller_id = current_user.id if current_user else order.seller_id
    v_tx_id = generate_verification_tx_id()

    submission = PaymentSubmission(
        order_id=order.id,
        seller_id=seller_id,
        verification_tx_id=v_tx_id,
        submitted_tx_id=submitted_tx_id,
        screenshot_sha256=img_sha256,
        screenshot_phash=img_phash,
        screenshot_file_size=len(img_data) if img_data else None,
        extracted_amount=ext_amount,
        extracted_tx_id=ext_tx_id,
        extracted_date=ext_date,
        extracted_payee_name=ext_payee,
        risk_score=risk.score,
        risk_verdict=risk.verdict,
        risk_reasons_json=json.dumps([r.model_dump() for r in risk.reasons]),
        screenshot_viewpoint=viewpoint,
    )
    db.add(submission)
    db.flush()

    # Record tx reference fingerprint
    if tx_ref_for_check:
        from app.analysis.duplicate_detection import _hmac_fingerprint
        submission.tx_ref_hmac = _hmac_fingerprint(tx_ref_for_check)
        record_payment_reference(db, seller_id, order.id, submission.id, tx_ref_for_check)

    db.add(AuditEvent(
        user_id=seller_id,
        event_type="payment_verified" if current_user else "payment_submitted_by_buyer",
        entity_type="order",
        entity_id=order.id,
        detail=f"verdict={risk.verdict} score={risk.score} tx_id={v_tx_id} by={'seller' if current_user else 'buyer'}",
    ))
    db.commit()

    # Build extracted fields for response
    ext_out: Optional[ExtractedPaymentFields] = None
    if extracted:
        ext_out = ExtractedPaymentFields(
            amount=extracted.get("amount"),
            currency=extracted.get("currency", "INR"),
            raw_amount_text=extracted.get("raw_amount_text"),
            tx_id=extracted.get("tx_id"),
            utr=extracted.get("utr"),
            payee_name=extracted.get("payee_name"),
            payee_upi_id=extracted.get("payee_upi_id"),
            date_str=extracted.get("date_str"),
            time_str=extracted.get("time_str"),
            app_indicator=extracted.get("app_indicator"),
            status_text=extracted.get("status_text"),
            viewpoint=extracted.get("viewpoint", "unknown"),
            ocr_confidence=extracted.get("ocr_confidence"),
            engine_used=extracted.get("engine_used"),
            field_confidence=extracted.get("field_confidence"),
            uncertain_fields=extracted.get("uncertain_fields", []),
            warnings=extracted.get("warnings", []),
        )

    # Comparison summary for compatibility with both new and legacy frontends
    comparison_summary = {
        "expected_amount": order.expected_amount,
        "expected_payee_name": order.expected_payee_name,
        "expected_upi_id": order.expected_upi_id,
        "amount_match": ext_amount is not None and abs(ext_amount - order.expected_amount) < 0.01,
        "payee_name_match": (
            bool(ext_payee and order.expected_payee_name and (
                ext_payee.lower() in order.expected_payee_name.lower() or
                order.expected_payee_name.lower() in ext_payee.lower()
            ))
        ),
        "upi_match": bool(
            extracted and extracted.get("payee_upi_id") and order.expected_upi_id and
            str(extracted.get("payee_upi_id") or "").lower() == str(order.expected_upi_id or "").lower()
        ),
    }

    return CrossVerifyResult(
        order_id=order.id,
        order_referral_code=order_referral_code,
        verification_tx_id=v_tx_id,
        expected_amount=order.expected_amount,
        expected_payee_name=order.expected_payee_name,
        expected_upi_id=order.expected_upi_id,
        extracted_fields=ext_out,
        extracted=extracted,
        comparison=comparison_summary,
        submitted_tx_id=submitted_tx_id,
        risk=risk,
        duplicate_warning=bool(
            (duplicate_ref and duplicate_ref.get("duplicate_found"))
            or (duplicate_img and duplicate_img.get("duplicate_found"))
        ),
        duplicate_details=(
            (duplicate_ref or {}).get("message") or (duplicate_img or {}).get("message")
        ),
        submission_id=submission.id,
    )


@router.get("/api/payments/history")
def payment_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 20,
):
    submissions = (
        db.query(PaymentSubmission)
        .filter(PaymentSubmission.seller_id == current_user.id)
        .order_by(PaymentSubmission.created_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for s in submissions:
        reasons = []
        if s.risk_reasons_json:
            try:
                reasons = json.loads(s.risk_reasons_json)
            except Exception:
                pass
        result.append({
            "submission_id": s.id,
            "order_id": s.order_id,
            "verification_tx_id": s.verification_tx_id,
            "submitted_tx_id": s.submitted_tx_id,
            "extracted_amount": s.extracted_amount,
            "extracted_tx_id": s.extracted_tx_id,
            "extracted_payee_name": s.extracted_payee_name,
            "risk_score": s.risk_score,
            "risk_verdict": s.risk_verdict,
            "screenshot_viewpoint": s.screenshot_viewpoint,
            "created_at": s.created_at.isoformat(),
            "reasons": reasons,
        })
    return result


@router.post("/api/orders/{order_id}/confirm-payment")
def confirm_payment(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Seller manually confirms they have seen the bank credit.
    This is NOT automated payment verification.
    """
    order = db.query(Order).filter(
        Order.id == order_id, Order.seller_id == current_user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Order is cancelled.")

    order.status = "seller_confirmed"
    db.add(AuditEvent(
        user_id=current_user.id,
        event_type="payment_confirmed_by_seller",
        entity_type="order",
        entity_id=order.id,
    ))
    db.commit()
    return {
        "message": "Order marked as seller-confirmed. This records your manual confirmation after checking your bank or UPI app.",
        "order_id": order_id,
        "status": "seller_confirmed",
    }


@router.post("/api/orders/{order_id}/mark-review")
def mark_needs_review(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id, Order.seller_id == current_user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    order.status = "needs_review"
    db.add(AuditEvent(
        user_id=current_user.id,
        event_type="order_flagged_for_review",
        entity_type="order",
        entity_id=order.id,
    ))
    db.commit()
    return {"message": "Order flagged for review.", "order_id": order_id}
