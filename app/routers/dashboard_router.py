"""
Dashboard routes:
  GET /api/dashboard/stats
  GET /api/dashboard/activity
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import AuditEvent, Order, PaymentSubmission, PhotoCertificate, Product, User
from app.schemas import ActivityItem, DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sid = current_user.id

    def count_orders(status: str) -> int:
        return db.query(Order).filter(Order.seller_id == sid, Order.status == status).count()

    suspicious = (
        db.query(PaymentSubmission)
        .filter(
            PaymentSubmission.seller_id == sid,
            PaymentSubmission.risk_verdict == "suspicious",
        )
        .count()
    )

    return DashboardStats(
        total_orders=db.query(Order).filter(Order.seller_id == sid).count(),
        pending_orders=count_orders("pending"),
        needs_review_orders=count_orders("needs_review"),
        confirmed_orders=count_orders("seller_confirmed"),
        cancelled_orders=count_orders("cancelled"),
        suspicious_submissions=suspicious,
        total_products=db.query(Product).filter(Product.seller_id == sid, Product.is_active == True).count(),
        total_certificates=db.query(PhotoCertificate).filter(PhotoCertificate.seller_id == sid).count(),
    )


@router.get("/activity", response_model=list[ActivityItem])
def dashboard_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 15,
):
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.user_id == current_user.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [ActivityItem.model_validate(e) for e in events]
