"""
Image forensics checks for payment screenshots.
Provides supporting evidence only — results are NOT definitive proof of fraud.

Checks:
  1. File metadata (EXIF) inspection
  2. Compression / resampling clues
  3. Error Level Analysis (ELA) approximation
  4. Perceptual hash comparison
  5. SHA-256 file hash
"""
from __future__ import annotations

import hashlib
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from PIL import Image, ExifTags
import imagehash
import cv2
import numpy as np

_PIL_AVAILABLE = True
_CV2_AVAILABLE = True


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_phash(img_bytes: bytes) -> Optional[str]:
    """Compute perceptual hash. Returns None if unavailable."""
    if not _PIL_AVAILABLE:
        return None
    try:
        img = Image.open(io.BytesIO(img_bytes))
        return str(imagehash.phash(img))
    except Exception as e:
        logger.debug("phash failed: %s", type(e).__name__)
        return None


def phash_distance(h1: str, h2: str) -> Optional[int]:
    """Hamming distance between two hex phash strings. None on error."""
    if not _PIL_AVAILABLE:
        return None
    try:
        ih1 = imagehash.hex_to_hash(h1)
        ih2 = imagehash.hex_to_hash(h2)
        return int(ih1 - ih2)
    except Exception:
        return None


def _extract_exif(img: "Image.Image") -> dict:
    """Extract a subset of EXIF fields (no personal data)."""
    exif_data = {}
    try:
        getexif_fn = getattr(img, "_getexif", None)
        raw_exif = getexif_fn() if callable(getexif_fn) else None
        if isinstance(raw_exif, dict):
            for tag_id, value in raw_exif.items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                # Only capture non-sensitive tags
                safe_tags = {
                    "Make", "Model", "Software", "DateTime", "DateTimeOriginal",
                    "ImageWidth", "ImageLength", "Orientation", "ResolutionUnit",
                    "XResolution", "YResolution", "ExifImageWidth", "ExifImageHeight",
                }
                if tag in safe_tags:
                    exif_data[tag] = str(value)
    except Exception:
        pass
    return exif_data


def _ela_score(img_bytes: bytes, quality: int = 90) -> Optional[float]:
    """
    Approximate Error Level Analysis.
    Re-saves the image at a given quality and computes mean absolute difference.
    Higher scores suggest potential re-compression or editing artefacts.
    Returns None if unavailable.
    """
    if not _PIL_AVAILABLE:
        return None
    try:
        original = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        buf = io.BytesIO()
        original.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        recompressed = Image.open(buf).convert("RGB")

        orig_arr = np.array(original, dtype=np.float32)
        recomp_arr = np.array(recompressed, dtype=np.float32)
        diff = np.abs(orig_arr - recomp_arr)
        return float(np.mean(diff))
    except Exception as e:
        logger.debug("ELA failed: %s", type(e).__name__)
        return None


def analyze_image(img_bytes: bytes) -> dict:
    """
    Run all forensics checks on an image.
    Returns a dict with findings and observation notes.
    Never treats any single check as definitive fraud evidence.
    """
    findings: list[dict] = []
    observations: list[str] = []

    # 1. Basic file info
    sha256 = compute_sha256(img_bytes)
    phash_val = compute_phash(img_bytes)

    file_size = len(img_bytes)
    width = height = None
    exif = {}
    has_exif = False

    if _PIL_AVAILABLE:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            width, height = img.size
            exif = _extract_exif(img)
            has_exif = bool(exif)
        except Exception as e:
            observations.append(f"Could not open image for metadata inspection: {type(e).__name__}")

    # 2. EXIF checks
    if has_exif:
        software = exif.get("Software", "").lower()
        if any(kw in software for kw in ["photoshop", "gimp", "lightroom", "snapseed", "picsart"]):
            findings.append({
                "check": "exif_software",
                "level": "warning",
                "detail": f"Image was processed by editing software ({exif['Software']}).",
            })
        else:
            findings.append({
                "check": "exif_software",
                "level": "ok",
                "detail": "No known image-editing software detected in EXIF.",
            })
    else:
        observations.append(
            "No EXIF metadata found. Screenshots often lack EXIF, so this is not unusual."
        )

    # 3. ELA
    ela = _ela_score(img_bytes)
    if ela is not None:
        if ela > 8.0:
            findings.append({
                "check": "ela",
                "level": "warning",
                "detail": (
                    f"Error Level Analysis score is elevated ({ela:.1f}). "
                    "This may indicate re-compression or editing, but can also occur "
                    "due to lossy screenshot encoding."
                ),
            })
        else:
            findings.append({
                "check": "ela",
                "level": "ok",
                "detail": f"Error Level Analysis score is within normal range ({ela:.1f}).",
            })

    # 4. File size sanity check
    if file_size < 5_000:
        findings.append({
            "check": "file_size",
            "level": "warning",
            "detail": "File is unusually small for a payment screenshot. Could be a thumbnail or test image.",
        })

    return {
        "sha256": sha256,
        "phash": phash_val,
        "file_size_bytes": file_size,
        "image_width": width,
        "image_height": height,
        "has_exif": has_exif,
        "exif_safe_fields": exif,
        "ela_score": ela,
        "findings": findings,
        "observations": observations,
        "disclaimer": (
            "Image forensics results are supporting observations only. "
            "A normal-looking screenshot is not proof of genuine payment, "
            "and an edited-looking screenshot is not definitive proof of fraud."
        ),
    }
