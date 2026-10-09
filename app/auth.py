"""Seller registration, login, and JWT authentication for TrustCheck."""

from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from app.db import get_connection


JWT_SECRET_ENV = "TRUSTCHECK_JWT_SECRET"
# A fresh random key is used for local development when no environment value
# is configured. Set TRUSTCHECK_JWT_SECRET to keep tokens valid across restarts.
JWT_SECRET = os.environ.get(JWT_SECRET_ENV, "").strip() or secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_LIFETIME = timedelta(hours=24)

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    shop_name: str = Field(min_length=1)
    upi_id: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginRequest(BaseModel):
    phone: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _public_seller(row: sqlite3.Row) -> dict[str, str]:
    """Return seller fields that are safe to include in an API response."""
    return {
        "seller_id": row["seller_id"],
        "name": row["name"],
        "phone": row["phone"],
        "shop_name": row["shop_name"],
        "upi_id": row["upi_id"],
    }


def _create_access_token(seller_id: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": seller_id,
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_LIFETIME).timestamp()),
    }
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _authentication_response(seller: dict[str, str]) -> dict[str, Any]:
    return {"token": _create_access_token(seller["seller_id"]), "seller": seller}


def _clean_required_fields(values: dict[str, str]) -> dict[str, str]:
    cleaned = {key: value.strip() for key, value in values.items()}
    if any(not value for value in cleaned.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Required fields cannot be blank.",
        )
    return cleaned


@router.post("/register")
def register(payload: RegisterRequest) -> dict[str, Any]:
    fields = _clean_required_fields(
        {
            "name": payload.name,
            "phone": payload.phone,
            "shop_name": payload.shop_name,
            "upi_id": payload.upi_id,
        }
    )
    # Passwords are not trimmed; whitespace may be part of the chosen password.
    if not payload.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password cannot be blank.",
        )

    seller_id = secrets.token_urlsafe(18)
    created_at = datetime.now(timezone.utc).isoformat()
    password_hash = password_context.hash(payload.password)

    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO sellers
                    (seller_id, name, phone, shop_name, upi_id, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seller_id,
                    fields["name"],
                    fields["phone"],
                    fields["shop_name"],
                    fields["upi_id"],
                    password_hash,
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT seller_id, name, phone, shop_name, upi_id FROM sellers WHERE seller_id = ?",
                (seller_id,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A seller with this phone number already exists.",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The seller account could not be created. Please try again.",
        )
    return _authentication_response(_public_seller(row))


@router.post("/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    phone = payload.phone.strip()
    if not phone:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Phone cannot be blank.",
        )

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT seller_id, name, phone, shop_name, upi_id, password_hash
            FROM sellers
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

    if row is None or not password_context.verify(payload.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phone number or password is incorrect.",
        )

    return _authentication_response(_public_seller(row))


def get_current_seller(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, str]:
    """Validate a bearer token and return its active seller account."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid seller login is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        claims = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise unauthorized from exc

    seller_id = claims.get("sub")
    if not isinstance(seller_id, str) or not seller_id:
        raise unauthorized

    with get_connection() as connection:
        row = connection.execute(
            "SELECT seller_id, name, phone, shop_name, upi_id FROM sellers WHERE seller_id = ?",
            (seller_id,),
        ).fetchone()

    if row is None:
        raise unauthorized
    return _public_seller(row)


__all__ = ["get_current_seller", "router"]
