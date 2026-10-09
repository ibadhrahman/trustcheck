"""
Seller profile routes:
  GET   /api/seller/profile
  PATCH /api/seller/profile
  GET   /api/seller/referral-code
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import SellerProfile, User
from app.referral_codes import create_seller_referral_code
from app.schemas import SellerProfileOut, SellerProfileUpdate

router = APIRouter(prefix="/api/seller", tags=["seller"])


def _get_or_create_profile(db: Session, user: User) -> SellerProfile:
    if user.profile:
        return user.profile
    profile = SellerProfile(user_id=user.id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/profile", response_model=SellerProfileOut)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_or_create_profile(db, current_user)
    return SellerProfileOut.model_validate(profile)


@router.patch("/profile", response_model=SellerProfileOut)
def update_profile(
    payload: SellerProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_or_create_profile(db, current_user)
    update_data = payload.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return SellerProfileOut.model_validate(profile)


@router.get("/referral-code")
def get_referral_code(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    src = current_user.seller_referral_code
    if not src:
        src = create_seller_referral_code(db, current_user.id)
    return {"seller_referral_code": src.code}
