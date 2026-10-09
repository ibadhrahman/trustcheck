"""
Products and photo certificate routes:
  POST /api/products
  GET  /api/products
  GET  /api/products/{product_id}
  POST /api/products/{product_id}/certificate  (multipart upload)
  POST /api/certificates/verify                (multipart upload)
  GET  /api/ledger/status
"""
from __future__ import annotations

import hashlib
import io
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.ledger import append_ledger_entry, verify_ledger_integrity
from app.models import AuditEvent, PhotoCertificate, Product, User
from app.schemas import (
    CertificateOut,
    CertificateVerifyResult,
    LedgerStatusOut,
    ProductCreate,
    ProductOut,
)

router = APIRouter(tags=["products"])

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


def _validate_image_upload(file: UploadFile) -> bytes:
    """Read and validate an uploaded image. Returns raw bytes."""
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{file.content_type}' not supported. Use JPEG, PNG, or WebP.",
        )
    data = file.file.read()
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB.",
        )
    return data


def _compute_image_metadata(data: bytes) -> dict:
    sha256 = hashlib.sha256(data).hexdigest()
    phash_val: Optional[str] = None
    width = height = None
    try:
        from PIL import Image
        import imagehash, io as _io
        img = Image.open(_io.BytesIO(data))
        width, height = img.size
        phash_val = str(imagehash.phash(img))
    except Exception:
        pass
    return {"sha256": sha256, "phash": phash_val, "width": width, "height": height}


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@router.post("/api/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = Product(
        seller_id=current_user.id,
        name=payload.name,
        description=payload.description,
        price=payload.price,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    db.add(AuditEvent(user_id=current_user.id, event_type="product_created", entity_type="product", entity_id=product.id))
    db.commit()
    out = ProductOut.model_validate(product)
    out.certificate_count = len(product.certificates)
    return out


@router.get("/api/products", response_model=list[ProductOut])
def list_products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    products = db.query(Product).filter(Product.seller_id == current_user.id, Product.is_active == True).all()
    result = []
    for p in products:
        out = ProductOut.model_validate(p)
        out.certificate_count = len(p.certificates)
        result.append(out)
    return result


@router.get("/api/products/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == product_id, Product.seller_id == current_user.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    out = ProductOut.model_validate(product)
    out.certificate_count = len(product.certificates)
    return out


# ---------------------------------------------------------------------------
# Photo Certificates
# ---------------------------------------------------------------------------

@router.post("/api/products/{product_id}/certificate", response_model=CertificateOut, status_code=201)
def create_certificate(
    product_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Ownership check
    product = db.query(Product).filter(
        Product.id == product_id, Product.seller_id == current_user.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    data = _validate_image_upload(file)
    meta = _compute_image_metadata(data)

    cert_id = secrets.token_hex(16)  # 32-char hex certificate ID

    cert = PhotoCertificate(
        product_id=product_id,
        seller_id=current_user.id,
        certificate_id=cert_id,
        filename=file.filename or "upload",
        sha256_hash=meta["sha256"],
        phash=meta["phash"],
        file_size_bytes=len(data),
        image_width=meta["width"],
        image_height=meta["height"],
        mime_type=file.content_type,
    )
    db.add(cert)
    db.flush()

    # Append ledger entry
    append_ledger_entry(
        db,
        certificate_id=cert.id,
        event_type="certificate_created",
        event_data={
            "product_id": product_id,
            "sha256": meta["sha256"],
            "filename": file.filename,
        },
    )
    db.add(AuditEvent(
        user_id=current_user.id,
        event_type="certificate_created",
        entity_type="certificate",
        entity_id=cert.id,
    ))
    db.commit()
    db.refresh(cert)
    return CertificateOut.model_validate(cert)


@router.post("/api/certificates/verify", response_model=CertificateVerifyResult)
def verify_certificate(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if an uploaded image matches any certified product image."""
    data = _validate_image_upload(file)
    meta = _compute_image_metadata(data)

    # Exact match
    exact = db.query(PhotoCertificate).filter(
        PhotoCertificate.sha256_hash == meta["sha256"],
        PhotoCertificate.seller_id == current_user.id,
    ).first()
    if exact:
        return CertificateVerifyResult(
            match_type="exact",
            sha256_match=True,
            phash_match=True,
            phash_distance=0,
            message="Exact match: this file's SHA-256 hash matches a certified product image.",
            certificate=CertificateOut.model_validate(exact),
        )

    # Perceptual similarity
    if meta["phash"]:
        from app.analysis.forensics import phash_distance
        all_certs = db.query(PhotoCertificate).filter(
            PhotoCertificate.seller_id == current_user.id,
            PhotoCertificate.phash != None,
        ).all()
        best_dist = None
        best_cert = None
        for c in all_certs:
            if not c.phash:
                continue
            d = phash_distance(meta["phash"], c.phash)
            if d is not None and (best_dist is None or d < best_dist):
                best_dist = d
                best_cert = c
        if best_cert and best_dist is not None and best_dist <= settings.phash_similarity_threshold:
            return CertificateVerifyResult(
                match_type="similar",
                sha256_match=False,
                phash_match=True,
                phash_distance=best_dist,
                message=(
                    f"Perceptual match: image is visually similar to a certified image "
                    f"(distance {best_dist}). "
                    "This indicates similarity, not proof of identity."
                ),
                certificate=CertificateOut.model_validate(best_cert),
            )

    return CertificateVerifyResult(
        match_type="no_match",
        sha256_match=False,
        phash_match=False,
        phash_distance=None,
        message="No matching certified image found in your product catalogue.",
        certificate=None,
    )


@router.get("/api/ledger/status", response_model=LedgerStatusOut)
def ledger_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = verify_ledger_integrity(db)
    return LedgerStatusOut(**result)
