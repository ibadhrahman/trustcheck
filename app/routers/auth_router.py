"""
Authentication routes:
  POST /api/auth/register
  POST /api/auth/login
  GET  /api/auth/me
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.db import get_db
from app.models import AuditEvent, SellerProfile, User
from app.referral_codes import create_seller_referral_code
from app.schemas import LoginRequest, MeResponse, RegisterRequest, SellerProfileOut, Token, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # Check duplicate email
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()  # get user.id

    # Create seller profile
    profile = SellerProfile(
        user_id=user.id,
        business_name=payload.business_name,
        contact_name=payload.contact_name,
        phone=payload.phone,
        upi_id=payload.upi_id,
    )
    db.add(profile)
    db.flush()

    # Generate seller referral code
    create_seller_referral_code(db, user.id)

    # Audit event
    db.add(AuditEvent(user_id=user.id, event_type="user_registered"))
    db.commit()

    token = create_access_token(user.id)
    return Token(access_token=token)


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )
    db.add(AuditEvent(user_id=user.id, event_type="user_login"))
    db.commit()
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = current_user.profile
    src = current_user.seller_referral_code
    return MeResponse(
        user=UserOut.model_validate(current_user),
        profile=SellerProfileOut.model_validate(profile) if profile else None,
        seller_referral_code=src.code if src else None,
    )
