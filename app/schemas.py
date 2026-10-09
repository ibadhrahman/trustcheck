"""
Pydantic schemas for request/response validation.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------

class RiskReason(BaseModel):
    level: str  # ok | warning | error
    text: str


class RiskResult(BaseModel):
    score: int
    verdict: str  # genuine | careful | suspicious
    reasons: list[RiskReason]
    details: dict[str, Any] = {}
    heatmap_png_base64: Optional[str] = None
    npci_validation: Optional[dict[str, Any]] = None
    disclaimer: str = (
        "Risk estimate only — not proof of payment. "
        "Confirm the credit in your bank or UPI app before dispatching."
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)
    upi_id: Optional[str] = Field(None, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Seller Profile
# ---------------------------------------------------------------------------

class SellerProfileOut(BaseModel):
    business_name: Optional[str]
    contact_name: Optional[str]
    phone: Optional[str]
    upi_id: Optional[str]
    bio: Optional[str]

    model_config = {"from_attributes": True}


class SellerProfileUpdate(BaseModel):
    business_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)
    upi_id: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)


class MeResponse(BaseModel):
    user: UserOut
    profile: Optional[SellerProfileOut]
    seller_referral_code: Optional[str]


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: float = Field(gt=0)


class ProductOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    is_active: bool
    created_at: datetime.datetime
    certificate_count: int = 0

    model_config = {"from_attributes": True}


class CertificateOut(BaseModel):
    id: int
    certificate_id: str
    product_id: int
    filename: str
    sha256_hash: str
    phash: Optional[str]
    file_size_bytes: int
    image_width: Optional[int]
    image_height: Optional[int]
    mime_type: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class CertificateVerifyResult(BaseModel):
    match_type: str  # exact | similar | no_match
    sha256_match: bool
    phash_match: bool
    phash_distance: Optional[int]
    message: str
    certificate: Optional[CertificateOut]


class LedgerStatusOut(BaseModel):
    total_entries: int
    is_intact: bool
    first_entry_time: Optional[datetime.datetime]
    last_entry_time: Optional[datetime.datetime]
    broken_at_entry: Optional[int]
    message: str


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class OrderCreate(BaseModel):
    product_id: Optional[int] = None
    quantity: int = Field(default=1, ge=1)
    expected_amount: float = Field(gt=0)
    expected_payee_name: Optional[str] = Field(None, max_length=200)
    expected_upi_id: Optional[str] = Field(None, max_length=100)
    customer_label: Optional[str] = Field(None, max_length=200)
    private_note: Optional[str] = Field(None, max_length=1000)


class ReferralCodeOut(BaseModel):
    code: str
    shareable_message: str


class OrderOut(BaseModel):
    id: int
    product_id: Optional[int]
    quantity: int
    expected_amount: float
    expected_payee_name: Optional[str]
    expected_upi_id: Optional[str]
    customer_label: Optional[str]
    status: str
    last_risk_verdict: Optional[str]
    last_risk_score: Optional[int]
    created_at: datetime.datetime
    referral_code: Optional[str] = None
    shareable_message: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Payment Verification
# ---------------------------------------------------------------------------

class PaymentAnalyzeRequest(BaseModel):
    order_referral_code: str
    submitted_tx_id: Optional[str] = Field(None, max_length=100)


class ExtractedPaymentFields(BaseModel):
    amount: Optional[float] = None
    currency: Optional[str] = "INR"
    raw_amount_text: Optional[str] = None
    tx_id: Optional[str] = None
    utr: Optional[str] = None
    payee_name: Optional[str] = None
    payee_upi_id: Optional[str] = None
    date_str: Optional[str] = None
    time_str: Optional[str] = None
    app_indicator: Optional[str] = None
    status_text: Optional[str] = None
    viewpoint: str = "unknown"  # payer | receiver | unknown
    ocr_confidence: Optional[float] = None
    engine_used: Optional[str] = None
    field_confidence: Optional[dict] = None
    uncertain_fields: list[str] = []
    warnings: list[str] = []


class CrossVerifyResult(BaseModel):
    order_id: int
    order_referral_code: str
    verification_tx_id: Optional[str] = None
    expected_amount: float
    expected_payee_name: Optional[str] = None
    expected_upi_id: Optional[str] = None
    extracted_fields: Optional[ExtractedPaymentFields] = None
    # Compatibility aliases for frontends
    extracted: Optional[dict] = None
    comparison: Optional[dict] = None
    submitted_tx_id: Optional[str] = None
    risk: RiskResult
    duplicate_warning: bool
    duplicate_details: Optional[str] = None
    submission_id: Optional[int] = None
    npci_validation: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Scam Checker
# ---------------------------------------------------------------------------

class ScamCheckRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    content_type: str = Field(default="message")  # message | url | upi_id | other

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        allowed = {"message", "sms", "whatsapp", "email", "url", "upi_id", "other"}
        if v not in allowed:
            raise ValueError(f"content_type must be one of {allowed}")
        return v


class ScamIndicator(BaseModel):
    pattern: str
    description: str
    severity: str  # low | medium | high


class ScamCheckResult(BaseModel):
    risk_score: int
    verdict: str  # safe | caution | dangerous
    indicators: list[ScamIndicator]
    safe_next_steps: list[str]
    disclaimer: str = (
        "This is a rule-based heuristic check. "
        "It cannot guarantee a message or link is safe or malicious."
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_orders: int
    pending_orders: int
    needs_review_orders: int
    confirmed_orders: int
    cancelled_orders: int
    suspicious_submissions: int
    total_products: int
    total_certificates: int


class ActivityItem(BaseModel):
    event_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    detail: Optional[str] = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
