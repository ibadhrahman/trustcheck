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
from app.analysis.npci_validator import validate_utr_npci
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


def _load_json_dict(value: Optional[str]) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _stored_submission_result(submission: PaymentSubmission) -> CrossVerifyResult:
    """Return the saved analysis for a seller-provided buyer verification ID."""
    order = submission.order
    extracted = _load_json_dict(submission.extracted_json)
    forensics = _load_json_dict(submission.forensics_json)
    duplicates = _load_json_dict(submission.duplicate_json)
    comparison = _load_json_dict(submission.comparison_json)
    if not comparison:
        comparison = {
            "expected_amount": order.expected_amount,
            "expected_payee_name": order.expected_payee_name,
            "extracted_amount": submission.extracted_amount,
            "extracted_payee_name": submission.extracted_payee_name,
            "extracted_tx_id": submission.extracted_tx_id,
        }

    reasons = []
    if submission.risk_reasons_json:
        try:
            parsed_reasons = json.loads(submission.risk_reasons_json)
            if isinstance(parsed_reasons, list):
                reasons = [
                    RiskReason.model_validate(reason)
                    for reason in parsed_reasons
                    if isinstance(reason, dict)
                ]
        except (TypeError, ValueError):
            reasons = []

    npci_validation = comparison.get("npci_validation")
    risk = RiskResult(
        score=submission.risk_score or 0,
        verdict=submission.risk_verdict or "careful",
        reasons=reasons,
        details={"npci_validation": npci_validation} if npci_validation else {},
        npci_validation=npci_validation,
    )

    extracted_fields = None
    if extracted:
        extracted_fields = ExtractedPaymentFields.model_validate(extracted)
    elif any((submission.extracted_amount is not None, submission.extracted_tx_id, submission.extracted_payee_name)):
        extracted_fields = ExtractedPaymentFields(
            amount=submission.extracted_amount,
            tx_id=submission.extracted_tx_id,
            utr=submission.extracted_tx_id,
            payee_name=submission.extracted_payee_name,
            date_str=submission.extracted_date,
            viewpoint=submission.screenshot_viewpoint or "unknown",
        )

    transaction_duplicate = duplicates.get("transaction_reference") or {}
    screenshot_duplicate = duplicates.get("screenshot") or {}
    duplicate_matches = [
        duplicate.get("message") or f"{label} duplicate detected."
        for label, duplicate in (
            ("Transaction reference", transaction_duplicate),
            ("Screenshot", screenshot_duplicate),
        )
        if duplicate.get("duplicate_found")
    ]

    return CrossVerifyResult(
        order_id=order.id,
        order_referral_code=(order.referral_code.code if order.referral_code else submission.verification_tx_id or ""),
        verification_tx_id=submission.verification_tx_id,
        expected_amount=order.expected_amount,
        expected_payee_name=order.expected_payee_name,
        expected_upi_id=order.expected_upi_id,
        extracted_fields=extracted_fields,
        extracted=extracted or None,
        comparison=comparison or None,
        submitted_tx_id=submission.submitted_tx_id,
        risk=risk,
        duplicate_warning=bool(duplicate_matches),
        duplicate_details=" ".join(duplicate_matches) or None,
        submission_id=submission.id,
        npci_validation=npci_validation,
        forensics=forensics or None,
        duplicates=duplicates or None,
        image_metadata=(
            {
                "sha256": submission.screenshot_sha256,
                "phash": submission.screenshot_phash,
                "file_size_bytes": submission.screenshot_file_size,
            }
            if submission.screenshot_sha256 or submission.screenshot_phash
            else None
        ),
    )


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
        # Without a screenshot there is no visual evidence to assess.
        score += 20
        if submitted_tx_id:
            reasons.append(RiskReason(
                level="warning",
                text="A transaction reference was submitted, but no screenshot was provided for analysis.",
            ))
        else:
            reasons.append(RiskReason(
                level="warning",
                text="The order reference was found, but no payment screenshot was provided for analysis.",
            ))

    # --- Duplicate reference check ---
    if duplicate_ref and duplicate_ref.get("duplicate_found"):
        reasons.append(RiskReason(level="error", text=duplicate_ref["message"]))
        score += 40

    # --- Duplicate screenshot check ---
    if duplicate_img and duplicate_img.get("duplicate_found"):
        reasons.append(RiskReason(level="error", text=duplicate_img["message"]))
        score += 30

    # --- Forensics ---
    forensic_warning_found = False
    if forensics:
        for finding in forensics.get("findings", []):
            if finding["level"] == "warning":
                forensic_warning_found = True
                reasons.append(RiskReason(level="warning", text=f"[Forensics] {finding['detail']}"))
                score += 10
            elif finding["level"] == "ok":
                reasons.append(RiskReason(level="ok", text=f"[Forensics] {finding['detail']}"))

    # A forensic warning (such as EXIF identifying editing software) must
    # never be presented as a low-risk "genuine" result by itself.
    if forensic_warning_found:
        score = max(score, 20)

    # --- NPCI Julian-Cycle Banking Rail Audit (Innovation Engine) ---
    npci_val_dict = None
    ref_to_validate = None
    if extracted and (extracted.get("utr") or extracted.get("tx_id")):
        ref_to_validate = extracted.get("utr") or extracted.get("tx_id")
    elif submitted_tx_id:
        ref_to_validate = submitted_tx_id

    if ref_to_validate:
        claimed_date_input = None
        if extracted and extracted.get("date_str"):
            claimed_date_input = extracted.get("date_str")
        elif order and order.created_at:
            claimed_date_input = order.created_at.date()

        npci_res = validate_utr_npci(ref_to_validate, claimed_date=claimed_date_input)
        npci_val_dict = npci_res.to_dict()

        if npci_res.verdict == "impossible_julian_day":
            reasons.append(RiskReason(
                level="error",
                text=f"[NPCI Rail Audit] Impossible Julian cycle: {npci_res.detail}"
            ))
            score += 15
        elif npci_res.verdict == "future_utr":
            reasons.append(RiskReason(
                level="error",
                text=f"[NPCI Rail Audit] Chronometric anomaly: {npci_res.detail}"
            ))
            score += 15
        elif npci_res.verdict == "year_mismatch":
            reasons.append(RiskReason(
                level="error",
                text=f"[NPCI Rail Audit] Reference year mismatch: {npci_res.detail}"
            ))
            score += 10
        elif npci_res.verdict == "stale_utr":
            reasons.append(RiskReason(
                level="warning",
                text=f"[NPCI Rail Audit] Stale reference: {npci_res.detail}"
            ))
            score += 10
        elif npci_res.verdict == "valid":
            reasons.append(RiskReason(
                level="ok",
                text=f"[NPCI Rail Audit] Verified NPCI settlement rail (Julian Day {npci_res.decoded_julian_day:03d} -> {npci_res.decoded_date})."
            ))

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
        npci_validation=npci_val_dict,
        details={
            "ocr_available": any(get_ocr_availability().values()),
            "npci_validation": npci_val_dict,
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
    npci_val = None
    ref_found = (extracted or {}).get("utr") or (extracted or {}).get("tx_id")
    if ref_found:
        npci_res = validate_utr_npci(ref_found, claimed_date=(extracted or {}).get("date_str"))
        npci_val = npci_res.to_dict()
    return {
        "extracted": extracted,
        "forensics": {
            "sha256": forensics["sha256"],
            "phash": forensics["phash"],
            "findings": forensics["findings"],
            "observations": forensics["observations"],
            "disclaimer": forensics["disclaimer"],
        },
        "npci_validation": npci_val,
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

    # 0. Check if numeric order ID (e.g. "12", "#12", "ORDER 12")
    numeric_candidate = code_cleaned.replace("ORDER", "").replace("#", "").strip()
    if numeric_candidate.isdigit():
        order_by_id = db.query(Order).filter(Order.id == int(numeric_candidate)).first()
        if order_by_id:
            if current_user and order_by_id.seller_id != current_user.id:
                raise HTTPException(status_code=403, detail="Access denied.")
            order = order_by_id

    # A buyer verification ID identifies an existing saved analysis. Only its
    # owning seller may retrieve it, and reading it must not create a new scan.
    if code_cleaned.startswith("TXN-"):
        if not current_user:
            raise HTTPException(status_code=401, detail="Sign in as the seller to view this verification.")
        submission = (
            db.query(PaymentSubmission)
            .filter(
                PaymentSubmission.verification_tx_id == code_cleaned,
                PaymentSubmission.seller_id == current_user.id,
            )
            .first()
        )
        if not submission or not submission.order:
            raise HTTPException(status_code=404, detail="Verification reference not found.")
        return _stored_submission_result(submission)

    if not order:
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
                    detail="Order not found. Please check your Order ID or referral code.",
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
    comparison_summary = {
        "expected_amount": order.expected_amount,
        "expected_payee_name": order.expected_payee_name,
        "extracted_amount": ext_amount,
        "extracted_payee_name": ext_payee,
        "extracted_tx_id": ext_tx_id,
        "extracted_date": ext_date,
        "extracted_time": extracted.get("time_str") if extracted else None,
        "amount_match": ext_amount is not None and abs(ext_amount - order.expected_amount) < 0.01,
        "payee_name_match": (
            bool(
                ext_payee.lower().strip() in order.expected_payee_name.lower().strip()
                or order.expected_payee_name.lower().strip() in ext_payee.lower().strip()
            )
            if ext_payee and order.expected_payee_name else None
        ),
        "npci_validation": risk.npci_validation,
    }

    def duplicate_snapshot(result: Optional[dict]) -> dict:
        """Keep seller-visible duplicate evidence without another seller's record IDs."""
        if not result or not result.get("duplicate_found"):
            return {"duplicate_found": False}
        return {
            "duplicate_found": True,
            "match_type": result.get("match_type", "transaction_reference"),
            "phash_distance": result.get("phash_distance"),
            "first_seen_at": result.get("first_seen_at"),
            "message": result.get("message"),
        }

    duplicate_summary = {
        "transaction_reference": duplicate_snapshot(duplicate_ref),
        "screenshot": duplicate_snapshot(duplicate_img),
    }

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
        extracted_json=json.dumps(extracted, ensure_ascii=False, default=str) if extracted else None,
        forensics_json=json.dumps(forensics_result, ensure_ascii=False, default=str) if forensics_result else None,
        duplicate_json=json.dumps(duplicate_summary, ensure_ascii=False, default=str),
        comparison_json=json.dumps(comparison_summary, ensure_ascii=False, default=str),
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
    else:
        # Check if the order has prior submissions with extracted fields
        latest_sub = (
            db.query(PaymentSubmission)
            .filter(PaymentSubmission.order_id == order.id)
            .order_by(PaymentSubmission.created_at.desc())
            .first()
        )
        if latest_sub and (latest_sub.extracted_amount is not None or latest_sub.extracted_tx_id or latest_sub.submitted_tx_id):
            ext_out = ExtractedPaymentFields(
                amount=latest_sub.extracted_amount,
                currency="INR",
                tx_id=latest_sub.extracted_tx_id or latest_sub.submitted_tx_id,
                utr=latest_sub.extracted_tx_id,
                payee_name=latest_sub.extracted_payee_name,
                date_str=latest_sub.extracted_date,
                viewpoint=latest_sub.screenshot_viewpoint or "unknown",
            )

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
        npci_validation=risk.npci_validation,
        forensics=forensics_result,
        duplicates=duplicate_summary,
        image_metadata=(
            {
                "sha256": img_sha256,
                "phash": img_phash,
                "file_size_bytes": len(img_data) if img_data else None,
            }
            if img_data
            else None
        ),
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
    repaired_records = False
    for s in submissions:
        reasons = []
        if s.risk_reasons_json:
            try:
                reasons = json.loads(s.risk_reasons_json)
            except Exception:
                pass
        def load_json(value: Optional[str]) -> Optional[dict]:
            if not value:
                return None
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else None
            except (TypeError, ValueError):
                return None

        comparison = load_json(s.comparison_json)
        if comparison and "upi_match" in comparison:
            # Remove the retired check from older saved comparison snapshots.
            comparison.pop("upi_match", None)
            s.comparison_json = json.dumps(comparison, ensure_ascii=False)
            repaired_records = True
        forensics = load_json(s.forensics_json)
        extracted_fields = load_json(s.extracted_json) or {}
        npci_validation = (comparison or {}).get("npci_validation")
        if not npci_validation:
            reference = (
                extracted_fields.get("utr")
                or extracted_fields.get("tx_id")
                or s.extracted_tx_id
                or s.submitted_tx_id
            )
            if reference:
                npci_validation = validate_utr_npci(
                    reference,
                    claimed_date=extracted_fields.get("date_str") or s.extracted_date,
                ).to_dict()
                comparison = comparison or {}
                comparison["npci_validation"] = npci_validation
                s.comparison_json = json.dumps(comparison, ensure_ascii=False)
                repaired_records = True
        forensic_warning_found = bool(
            forensics and any(
                finding.get("level") == "warning"
                for finding in forensics.get("findings", [])
            )
        )
        if forensic_warning_found and (s.risk_score is None or s.risk_score < 20):
            # Correct older records created before forensic warnings received
            # a minimum "careful" score.
            s.risk_score = 20
            s.risk_verdict = "careful"
            repaired_records = True
        if comparison is None and s.order:
            comparison = {
                "expected_amount": s.order.expected_amount,
                "expected_payee_name": s.order.expected_payee_name,
            }
        result.append({
            "submission_id": s.id,
            "order_id": s.order_id,
            "verification_tx_id": s.verification_tx_id,
            "submitted_tx_id": s.submitted_tx_id,
            "extracted_amount": s.extracted_amount,
            "extracted_tx_id": s.extracted_tx_id,
            "extracted_payee_name": s.extracted_payee_name,
            "extracted_fields": extracted_fields,
            "forensics": forensics,
            "duplicates": load_json(s.duplicate_json),
            "comparison": comparison,
            "has_screenshot": bool(s.screenshot_sha256),
            "image_metadata": ({
                "sha256": s.screenshot_sha256,
                "phash": s.screenshot_phash,
                "file_size_bytes": s.screenshot_file_size,
            } if s.screenshot_sha256 else None),
            "risk_score": s.risk_score,
            "risk_verdict": s.risk_verdict,
            "screenshot_viewpoint": s.screenshot_viewpoint,
            "created_at": s.created_at.isoformat(),
            "reasons": reasons,
            "disclaimer": "Risk estimate only — not proof of payment.",
        })
    if repaired_records:
        db.commit()
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
