"""
SQLAlchemy ORM models for TrustCheck.
All tables are defined here.
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Users & Seller Profiles
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    profile: Mapped[Optional["SellerProfile"]] = relationship(
        "SellerProfile", back_populates="user", uselist=False
    )
    products: Mapped[list["Product"]] = relationship("Product", back_populates="seller")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="seller")
    seller_referral_code: Mapped[Optional["SellerReferralCode"]] = relationship(
        "SellerReferralCode", back_populates="seller", uselist=False
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship("AuditEvent", back_populates="user")


class BuyerAccount(Base):
    """Buyer identity used to claim private orders and submit outcomes."""
    __tablename__ = "buyer_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="buyer")
    outcomes: Mapped[list["OrderOutcome"]] = relationship("OrderOutcome", back_populates="buyer")


class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    business_name: Mapped[Optional[str]] = mapped_column(String(200))
    contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    upi_id: Mapped[Optional[str]] = mapped_column(String(100))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    user: Mapped["User"] = relationship("User", back_populates="profile")


# ---------------------------------------------------------------------------
# Referral Codes
# ---------------------------------------------------------------------------

class SellerReferralCode(Base):
    __tablename__ = "seller_referral_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    seller: Mapped["User"] = relationship("User", back_populates="seller_referral_code")

    __table_args__ = (UniqueConstraint("code", name="uq_seller_ref_code"),)


class OrderReferralCode(Base):
    __tablename__ = "order_referral_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    order: Mapped["Order"] = relationship("Order", back_populates="referral_code")
    seller: Mapped["User"] = relationship("User")

    __table_args__ = (UniqueConstraint("code", name="uq_order_ref_code"),)


# ---------------------------------------------------------------------------
# Products & Photo Certificates
# ---------------------------------------------------------------------------

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    seller: Mapped["User"] = relationship("User", back_populates="products")
    certificates: Mapped[list["PhotoCertificate"]] = relationship(
        "PhotoCertificate", back_populates="product"
    )
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="product")

    __table_args__ = (Index("ix_products_seller", "seller_id"),)


class PhotoCertificate(Base):
    __tablename__ = "photo_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    certificate_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    phash: Mapped[Optional[str]] = mapped_column(String(64))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    image_width: Mapped[Optional[int]] = mapped_column(Integer)
    image_height: Mapped[Optional[int]] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    product: Mapped["Product"] = relationship("Product", back_populates="certificates")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="certificate"
    )

    __table_args__ = (Index("ix_certs_seller", "seller_id"),)


class LedgerEntry(Base):
    """Append-only hash-linked integrity ledger for photo certificates."""
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    certificate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("photo_certificates.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_data: Mapped[Optional[str]] = mapped_column(Text)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_record_hash: Mapped[Optional[str]] = mapped_column(String(64))
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    certificate: Mapped["PhotoCertificate"] = relationship(
        "PhotoCertificate", back_populates="ledger_entries"
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    buyer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("buyer_accounts.id"))
    # HMAC of the private buyer order reference; plaintext is returned to the seller once.
    buyer_access_hmac: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    expected_amount: Mapped[float] = mapped_column(Float, nullable=False)
    expected_payee_name: Mapped[Optional[str]] = mapped_column(String(200))
    expected_upi_id: Mapped[Optional[str]] = mapped_column(String(100))
    customer_label: Mapped[Optional[str]] = mapped_column(String(200))
    private_note: Mapped[Optional[str]] = mapped_column(Text)
    # Status: pending | needs_review | seller_confirmed | cancelled
    status: Mapped[str] = mapped_column(String(30), default="pending")
    # Risk verdict kept separate from seller-confirmed status
    last_risk_verdict: Mapped[Optional[str]] = mapped_column(String(20))
    last_risk_score: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    seller: Mapped["User"] = relationship("User", back_populates="orders")
    buyer: Mapped[Optional["BuyerAccount"]] = relationship("BuyerAccount", back_populates="orders")
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="orders")
    referral_code: Mapped[Optional["OrderReferralCode"]] = relationship(
        "OrderReferralCode", back_populates="order", uselist=False
    )
    payment_submissions: Mapped[list["PaymentSubmission"]] = relationship(
        "PaymentSubmission", back_populates="order"
    )
    outcome: Mapped[Optional["OrderOutcome"]] = relationship(
        "OrderOutcome", back_populates="order", uselist=False
    )

    __table_args__ = (Index("ix_orders_seller", "seller_id"),)


class OrderOutcome(Base):
    """Current buyer outcome and private issue details for one order."""
    __tablename__ = "order_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, nullable=False)
    # Nullable for reports made with the private order reference and no buyer account.
    buyer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("buyer_accounts.id"))
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)  # received | problem
    reason: Mapped[Optional[str]] = mapped_column(String(40))
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # received | awaiting_seller | resolution_offered | resolved
    reported_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    buyer_received_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    problem_reported_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    response_deadline: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    seller_resolution_type: Mapped[Optional[str]] = mapped_column(String(30))
    seller_response: Mapped[Optional[str]] = mapped_column(Text)
    seller_responded_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    order: Mapped["Order"] = relationship("Order", back_populates="outcome")
    buyer: Mapped[Optional["BuyerAccount"]] = relationship("BuyerAccount", back_populates="outcomes")
    events: Mapped[list["OrderOutcomeEvent"]] = relationship(
        "OrderOutcomeEvent", back_populates="outcome", order_by="OrderOutcomeEvent.created_at"
    )

    __table_args__ = (Index("ix_order_outcomes_buyer", "buyer_id"), Index("ix_order_outcomes_status", "status"))


class OrderOutcomeEvent(Base):
    """Append-only history of buyer reports, seller offers, and buyer decisions."""
    __tablename__ = "order_outcome_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    outcome_id: Mapped[int] = mapped_column(ForeignKey("order_outcomes.id"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # buyer | seller
    actor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resolution_type: Mapped[Optional[str]] = mapped_column(String(30))
    message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    outcome: Mapped["OrderOutcome"] = relationship("OrderOutcome", back_populates="events")
    evidence: Mapped[list["OrderOutcomeEvidence"]] = relationship(
        "OrderOutcomeEvidence", back_populates="event"
    )


class OrderOutcomeEvidence(Base):
    """Private, normalized product/report images; accessible only to order parties."""
    __tablename__ = "order_outcome_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("order_outcome_events.id"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    event: Mapped["OrderOutcomeEvent"] = relationship("OrderOutcomeEvent", back_populates="evidence")


# ---------------------------------------------------------------------------
# Payment Submissions & References
# ---------------------------------------------------------------------------

class PaymentSubmission(Base):
    """Privacy-conscious record of each payment-proof submission."""
    __tablename__ = "payment_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # Unique TrustCheck verification transaction ID
    verification_tx_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    # Manually entered by seller / buyer
    submitted_tx_id: Mapped[Optional[str]] = mapped_column(String(100))
    # Screenshot metadata (no raw image stored)
    screenshot_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    screenshot_phash: Mapped[Optional[str]] = mapped_column(String(64))
    screenshot_file_size: Mapped[Optional[int]] = mapped_column(Integer)
    # OCR-extracted fields (minimum necessary)
    extracted_amount: Mapped[Optional[float]] = mapped_column(Float)
    extracted_tx_id: Mapped[Optional[str]] = mapped_column(String(100))
    extracted_date: Mapped[Optional[str]] = mapped_column(String(50))
    extracted_payee_name: Mapped[Optional[str]] = mapped_column(String(200))
    # Tx reference HMAC fingerprint for duplicate detection (not raw value)
    tx_ref_hmac: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    # Risk result
    risk_score: Mapped[Optional[int]] = mapped_column(Integer)
    risk_verdict: Mapped[Optional[str]] = mapped_column(String(20))
    risk_reasons_json: Mapped[Optional[str]] = mapped_column(Text)
    # Stored scan details for seller cross-checking without re-uploading
    extracted_json: Mapped[Optional[str]] = mapped_column(Text)
    forensics_json: Mapped[Optional[str]] = mapped_column(Text)
    duplicate_json: Mapped[Optional[str]] = mapped_column(Text)
    comparison_json: Mapped[Optional[str]] = mapped_column(Text)
    # Screenshot viewpoint: payer | receiver | unknown
    screenshot_viewpoint: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    order: Mapped["Order"] = relationship("Order", back_populates="payment_submissions")

    __table_args__ = (Index("ix_submissions_order", "order_id"),)


class PaymentReference(Base):
    """
    HMAC fingerprints of previously seen transaction references.
    Used for duplicate-reference detection without storing raw values.
    """
    __tablename__ = "payment_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payment_submissions.id"), nullable=False
    )
    tx_ref_hmac: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (Index("ix_pay_ref_hmac", "tx_ref_hmac"),)


# ---------------------------------------------------------------------------
# Scam Checks
# ---------------------------------------------------------------------------

class ScamCheck(Base):
    __tablename__ = "scam_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    # Store only minimal info — do not log full submitted text
    content_type: Mapped[str] = mapped_column(String(30))  # message | url | upi_id | other
    content_length: Mapped[int] = mapped_column(Integer)
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_verdict: Mapped[str] = mapped_column(String(20))
    indicators_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------------
# Audit Events
# ---------------------------------------------------------------------------

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    detail: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_events")

    __table_args__ = (Index("ix_audit_user", "user_id"),)
