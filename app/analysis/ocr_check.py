"""
OCR pipeline for payment screenshot analysis.

Supports Tesseract (via pytesseract) and RapidOCR.
Attempts to extract payment fields from common Indian UPI apps:
  Google Pay, PhonePe, Paytm, BHIM

IMPORTANT:
- Never guess an unreadable amount.
- Never substitute expected amounts for extracted amounts.
- Return null for fields that cannot be reliably extracted.
- Do not log full OCR text or full UPI IDs.
"""
from __future__ import annotations

import io
import importlib.util
import logging
from pathlib import Path
import re
import shutil
import threading
import warnings
from collections import Counter
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: PIL / OpenCV / pytesseract
# ---------------------------------------------------------------------------

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

_PIL_AVAILABLE = True
_CV2_AVAILABLE = importlib.util.find_spec("cv2") is not None

try:
    import pytesseract
    _tesseract_cmd = pytesseract.pytesseract.tesseract_cmd
    _TESSERACT_AVAILABLE = bool(
        shutil.which(_tesseract_cmd) or Path(_tesseract_cmd).is_file()
    )
except Exception:
    pytesseract = None  # type: ignore
    _TESSERACT_AVAILABLE = False

_RAPIDOCR_INSTALLED = importlib.util.find_spec("rapidocr_onnxruntime") is not None
_RAPIDOCR_LOAD_ATTEMPTED = False
_RAPIDOCR_LOAD_FAILED = False
_rapid_engine = None
_rapid_engine_lock = threading.Lock()


def _get_rapidocr_engine():
    """Load the ONNX OCR model on first use instead of slowing server startup."""
    global _RAPIDOCR_LOAD_ATTEMPTED, _RAPIDOCR_LOAD_FAILED, _rapid_engine

    if not _RAPIDOCR_INSTALLED or _RAPIDOCR_LOAD_FAILED:
        return None
    if _rapid_engine is not None:
        return _rapid_engine

    with _rapid_engine_lock:
        if _rapid_engine is not None or _RAPIDOCR_LOAD_FAILED:
            return _rapid_engine
        if _RAPIDOCR_LOAD_ATTEMPTED:
            return None
        _RAPIDOCR_LOAD_ATTEMPTED = True
        try:
            from rapidocr_onnxruntime import RapidOCR

            _rapid_engine = RapidOCR()
        except Exception as exc:
            _RAPIDOCR_LOAD_FAILED = True
            logger.warning("RapidOCR initialization failed: %s", type(exc).__name__)
    return _rapid_engine


def get_ocr_availability() -> dict:
    return {
        "deepseek": bool(settings.deepseek_enabled and (settings.deepseek_api_key or "").strip()),
        "gemini": bool(settings.gemini_enabled and (settings.gemini_api_key or "").strip()),
        "tesseract": _TESSERACT_AVAILABLE,
        "rapidocr": _RAPIDOCR_INSTALLED and not _RAPIDOCR_LOAD_FAILED,
        "pillow": _PIL_AVAILABLE,
        "opencv": _CV2_AVAILABLE,
    }


# ---------------------------------------------------------------------------
# Field extraction patterns
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Field extraction patterns & helpers
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS_RE = r"(?:[₹\u20b9\u56de\u00a5\?\$*]|Rs\.?|rs\.?|INR|inr|RS)"

_AMOUNT_PATTERNS = [
    # Explicit currency symbol followed by amount: ₹1,234.56, Rs. 1234, 回500.00, ?500.00, INR 500
    rf"{_CURRENCY_SYMBOLS_RE}\s*([0-9]{{1,3}}(?:,[0-9]{{2,3}})*(?:\.[0-9]{{1,2}})?|[0-9]+(?:\.[0-9]{{1,2}})?)",
    # Amount followed by currency symbol / suffix: 500 Rs, 500 INR, 500/-
    r"([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)\s*(?:[/-]|Rs\.?|INR)",
    # Contextual keywords: "Payment of ₹400", "Paid: 400", "Amount: 400", "Total: ₹400", "Debited: 400", "Money sent: 400"
    rf"(?:paid|paying|payment\s+of|amount|total|debited|sent|transferred|amt)[:\s]+{_CURRENCY_SYMBOLS_RE}?\s*([0-9]{{1,3}}(?:,[0-9]{{2,3}})*(?:\.[0-9]{{1,2}})?|[0-9]+(?:\.[0-9]{{1,2}})?)",
    # Amount followed by success words: "500 was successful", "1,250 paid successfully", "500.00 completed"
    r"([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)\s*(?:was\s+successful|paid\s+successfully|successfully\s+paid|completed|transferred|sent|debited)",
]

_PAYEE_LABELS = [
    r"(?:Banking\s+Name|Bank\s+Name)[:\s]+([^\r\n]+)",
    r"(?:Beneficiary(?:\s+Name)?|Payee(?:\s+Name)?|Receiver(?:\s+Name)?|Recipient(?:\s+Name)?|Merchant(?:\s+Name)?)[:\s]+([^\r\n]+)",
    r"(?:Paid\s+successfully\s+to|Money\s+sent\s+to|Transferred\s+to)[:\s]+([^\r\n]+)",
    r"(?:Paid\s+to|Paying\s+to|Payment\s+to|Sent\s+to|Credited\s+to)[:\s]+([^\r\n]+)",
    r"^To[:\s]+([^\r\n]+)",
]

_TX_ID_PATTERNS = [
    # PhonePe: T followed by 21 digits
    r"\b(T[0-9]{21})\b",
    # Generic 12-digit transaction IDs (BHIM, NPCI, UPI)
    r"\b([0-9]{12})\b",
    # UPI transaction ID label
    r"(?:UPI\s*(?:transaction\s*)?ID|Transaction\s*ID|Txn\s*ID|Ref\.?\s*No\.?)[:\s#]+([A-Za-z0-9]{8,25})",
    # Paytm reference number
    r"(?:Ref\.?\s*No\.?)[:\s#]+([0-9]{10,14})",
]

_UTR_PATTERNS = [
    r"(?:UTR|UTR\s*No\.?)[:\s#]+([A-Za-z0-9]{12,22})",
]

_DATE_PATTERNS = [
    # DD MMM YYYY or DD Mon YYYY
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4})\b",
    # DD/MM/YYYY or DD-MM-YYYY
    r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b",
    # D MMM without year (Paytm)
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?)\b",
]

_TIME_PATTERNS = [
    r"\b(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)\b",
]

_SUCCESS_KEYWORDS = [
    "payment successful", "paid successfully", "money sent", "transfer complete",
    "payment complete", "successfully paid", "payment done",
]

_PAYER_VIEW_KEYWORDS = ["paid to", "you paid", "money sent to", "transferred to"]
_RECEIVER_VIEW_KEYWORDS = ["received from", "money received", "payment received", "from"]

_APP_INDICATORS = {
    "googlepay": ["google pay", "gpay", "pay.google"],
    "phonepe": ["phonepe", "phone pe", "phonepetransaction"],
    "paytm": ["paytm"],
    "bhim": ["bhim", "bhim upi"],
}


def _clean_amount(raw: str) -> Optional[float]:
    """Parse amount string to float. Returns None on failure."""
    try:
        cleaned = raw.replace(",", "").strip()
        val = float(cleaned)
        if val <= 0 or val > 10_000_000:
            return None
        return round(val, 2)
    except (ValueError, AttributeError):
        return None


def _clean_payee_name(raw: str) -> Optional[str]:
    """Clean and validate an extracted payee/merchant name candidate."""
    if not raw:
        return None
    # Strip secondary qualifiers (UPI ID, parentheses, account numbers, labels)
    cand = re.split(r"\(|@|\bUPI\b|\bRef\b|\bTxn\b|\bUTR\b|\bDate\b|\bAmount\b|\bStatus\b| - ", raw)[0]
    cand = cand.strip(" .,:;-_\"'")
    if len(cand) < 2 or len(cand) > 80:
        return None
    lower = cand.lower()
    excluded = [
        "successful", "completed", "failed", "pending", "google pay", "phonepe",
        "paytm", "bhim", "payment", "upi", "done", "transferred", "transfer",
    ]
    if any(lower == ex or lower.startswith(ex + " ") for ex in excluded):
        return None
    return cand


def _extract_from_text(
    text: str,
    expected_amount: Optional[float] = None,
    expected_payee_name: Optional[str] = None,
) -> dict:
    """Extract structured fields from raw OCR text with multi-pass heuristics."""
    result: dict = {
        "amount": None,
        "tx_id": None,
        "utr": None,
        "payee_name": None,
        "payee_upi_id": None,
        "date_str": None,
        "time_str": None,
        "app_indicator": None,
        "status_text": None,
        "viewpoint": "unknown",
        "warnings": [],
    }

    lower = text.lower()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # 1. Amount Extraction
    # 1A. Standard regex patterns
    for pat in _AMOUNT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = _clean_amount(m.group(1))
            if val is not None:
                result["amount"] = val
                break

    # 1B. Standalone decimal lines (e.g. Google Pay '500.00' or RapidOCR '0500.00')
    if result["amount"] is None:
        for line in lines:
            m = re.match(r"^[^\w\d]*0?([0-9]{1,6}(?:,[0-9]{2,3})*\.[0-9]{2})[^\w\d]*$", line)
            if m:
                val = _clean_amount(m.group(1))
                if val is not None and val not in (2024.0, 2025.0, 2026.0, 2027.0):
                    result["amount"] = val
                    break

    # 1C. Standalone comma-formatted integer lines (e.g. PhonePe '1,250')
    if result["amount"] is None:
        for line in lines:
            m = re.match(r"^[^\w\d]*0?([0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]{2,6})[^\w\d]*$", line)
            if m:
                val = _clean_amount(m.group(1))
                if val is not None and val not in (2024.0, 2025.0, 2026.0, 2027.0):
                    result["amount"] = val
                    break

    # 1D. Corroborate with expected amount if present in screenshot text
    if result["amount"] is None and expected_amount and expected_amount > 0:
        amt_str = f"{expected_amount:.2f}"
        amt_int = f"{int(expected_amount)}" if expected_amount.is_integer() else amt_str
        if re.search(rf"\b0?(?:{re.escape(amt_str)}|{re.escape(amt_int)})\b", text):
            result["amount"] = expected_amount

    # 2. Transaction ID
    for pat in _TX_ID_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            tx = m.group(len(m.groups()))
            result["tx_id"] = tx.strip()
            break

    # 3. UTR
    for pat in _UTR_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["utr"] = m.group(1).strip()
            break

    # 4. Date
    for pat in _DATE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["date_str"] = m.group(1).strip()
            break

    # 5. Time
    for pat in _TIME_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["time_str"] = m.group(1).strip()
            break

    # 6. UPI ID
    upi_match = re.search(r"\b([a-zA-Z0-9.\-_]+@[a-zA-Z0-9]+)\b", text)
    if upi_match:
        result["payee_upi_id"] = upi_match.group(1)

    # 7. Payee Name Extraction
    # 7A. Explicit payee labels (Banking Name, Paid to, To:, Merchant, Beneficiary)
    for pat in _PAYEE_LABELS:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            cand = _clean_payee_name(m.group(1))
            if cand:
                result["payee_name"] = cand[:100]
                break

    # 7B. Layout-based detection (name immediately preceding UPI ID line, e.g. GPay)
    if result["payee_name"] is None:
        for i, line in enumerate(lines[:-1]):
            next_l = lines[i + 1]
            if re.search(r"\b[a-zA-Z0-9.\-_]+@[a-zA-Z0-9]+\b", next_l):
                cand = _clean_payee_name(line)
                if cand:
                    result["payee_name"] = cand[:100]
                    break

    # 7C. Match against expected payee name if found in text
    if result["payee_name"] is None and expected_payee_name:
        exp_low = expected_payee_name.lower().strip()
        for line in lines:
            c = _clean_payee_name(line)
            if c:
                c_low = c.lower()
                if exp_low in c_low or c_low in exp_low:
                    result["payee_name"] = c[:100]
                    break
                words = [w for w in exp_low.split() if len(w) >= 4]
                if words and any(w in c_low for w in words):
                    result["payee_name"] = c[:100]
                    break

    # 8. App indicator
    for app, keywords in _APP_INDICATORS.items():
        if any(kw in lower for kw in keywords):
            result["app_indicator"] = app
            break

    # 9. Status text
    for kw in _SUCCESS_KEYWORDS:
        if kw in lower:
            result["status_text"] = kw
            break

    # 10. Viewpoint detection
    if any(kw in lower for kw in _PAYER_VIEW_KEYWORDS):
        result["viewpoint"] = "payer"
    elif any(kw in lower for kw in _RECEIVER_VIEW_KEYWORDS):
        result["viewpoint"] = "receiver"
        result["warnings"].append(
            "Screenshot appears to show an incoming payment view, not a payment-made confirmation. "
            "Please review manually."
        )

    return result


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

def _preprocess_image_for_ocr(img_bytes: bytes) -> list[bytes]:
    """Return a list of preprocessed image variants for OCR passes."""
    if not _PIL_AVAILABLE:
        return [img_bytes]

    results = []

    try:
        from PIL import ImageStat
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        # Resize if too small (upscale mobile screenshots for clearer character resolution)
        w, h = img.size
        if max(w, h) < 900:
            scale = 900 / max(w, h)
            resample_filter = getattr(getattr(Image, "Resampling", None), "LANCZOS", getattr(Image, "LANCZOS", 1))
            img = img.resize((int(w * scale), int(h * scale)), resample_filter)

        # Pass 1: Original RGB (best for modern deep-learning OCR models like RapidOCR)
        buf1 = io.BytesIO()
        img.save(buf1, format="PNG")
        results.append(buf1.getvalue())

        # Pass 2: Grayscale with moderate contrast boost
        gray = img.convert("L")
        gray = ImageEnhance.Contrast(gray).enhance(1.6)
        buf2 = io.BytesIO()
        gray.save(buf2, format="PNG")
        results.append(buf2.getvalue())

        # Pass 3: Invert ONLY IF background is actually dark (dark mode screenshots)
        stat = ImageStat.Stat(img.convert("L"))
        if stat.mean and stat.mean[0] < 95:
            inverted = ImageOps.invert(img.convert("L"))
            buf3 = io.BytesIO()
            inverted.save(buf3, format="PNG")
            results.append(buf3.getvalue())

    except Exception as e:
        logger.warning("Image preprocessing failed: %s", type(e).__name__)
        results.append(img_bytes)

    return results


# ---------------------------------------------------------------------------
# OCR engines
# ---------------------------------------------------------------------------

def _ocr_tesseract(img_bytes: bytes) -> Optional[str]:
    if not _TESSERACT_AVAILABLE or pytesseract is None:
        return None
    try:
        img = Image.open(io.BytesIO(img_bytes))
        # PSM 6: assume a uniform block of text (good for UPI screens)
        config = "--oem 3 --psm 6"
        raw_text = pytesseract.image_to_string(img, config=config, lang="eng")
        if isinstance(raw_text, bytes):
            return raw_text.decode("utf-8", errors="replace")
        return str(raw_text) if raw_text is not None else None
    except Exception as e:
        logger.warning("Tesseract OCR failed: %s", type(e).__name__)
        return None


def _ocr_rapidocr(img_bytes: bytes) -> Optional[str]:
    engine = _get_rapidocr_engine()
    if engine is None:
        return None
    try:
        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        arr = np.array(img)
        result, _ = engine(arr)
        if result:
            return "\n".join(r[1] for r in result)
        return None
    except Exception as e:
        logger.warning("RapidOCR failed: %s", type(e).__name__)
        return None


def _run_ocr(img_bytes: bytes) -> tuple[Optional[str], float]:
    """
    Run OCR with the configured engine(s) and return (text, confidence_estimate).
    Returns (None, 0.0) if no OCR engine is available.
    """
    engine = settings.ocr_engine.lower()

    texts: list[str] = []

    if engine in ("tesseract", "auto"):
        t = _ocr_tesseract(img_bytes)
        if t:
            texts.append(t)

    if engine in ("rapidocr", "auto") and not texts:
        r = _ocr_rapidocr(img_bytes)
        if r:
            texts.append(r)

    if not texts:
        return None, 0.0

    # Use the longest result as most informative
    best = max(texts, key=len)
    confidence = 0.7 if len(best) > 50 else 0.4
    return best, confidence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_payment_fields(
    img_bytes: bytes,
    expected_amount: Optional[float] = None,
    expected_payee_name: Optional[str] = None,
) -> dict:
    """
    Main entry point. Preprocesses the image, runs OCR in multiple passes,
    and extracts structured payment fields.

    Optionally accepts expected_amount and expected_payee_name to cross-corroborate
    extracted values against known order/seller details without guessing.
    """
    availability = get_ocr_availability()
    if not availability["pillow"]:
        return _unavailable_result("Pillow (PIL) not installed. Cannot process images.")

    if not availability["tesseract"] and not availability["rapidocr"]:
        return _unavailable_result(
            "No OCR engine available. "
            "Install Tesseract (system package) + pytesseract, "
            "or install rapidocr-onnxruntime."
        )

    variants = _preprocess_image_for_ocr(img_bytes)

    all_results: list[dict] = []
    for variant in variants:
        text, conf = _run_ocr(variant)
        if text:
            fields = _extract_from_text(
                text,
                expected_amount=expected_amount,
                expected_payee_name=expected_payee_name,
            )
            fields["ocr_confidence"] = conf
            all_results.append(fields)

    if not all_results:
        return _unavailable_result("OCR returned no usable text.")

    # Merge results: majority consensus across passes, corroborate with expected amount
    merged = _merge_results(all_results, expected_amount=expected_amount)
    return merged


def _unavailable_result(warning: str) -> dict:
    return {
        "amount": None,
        "tx_id": None,
        "utr": None,
        "payee_name": None,
        "payee_upi_id": None,
        "date_str": None,
        "time_str": None,
        "app_indicator": None,
        "status_text": None,
        "viewpoint": "unknown",
        "ocr_confidence": 0.0,
        "warnings": [warning],
    }


def _merge_results(results: list[dict], expected_amount: Optional[float] = None) -> dict:
    """
    Merge multiple OCR pass results using consensus voting.
    Prioritizes expected amounts and high-frequency candidates to prevent noisy passes from discarding valid amounts.
    """
    merged = results[0].copy()

    # Collect all non-None amounts
    amounts = [r["amount"] for r in results if r.get("amount") is not None]

    if not amounts:
        merged["amount"] = None
        merged["warnings"] = merged.get("warnings", []) + [
            "Payment amount could not be read from the screenshot. Cannot confirm amount match."
        ]
    else:
        # 1. If an expected amount is specified and matches any pass candidate:
        if expected_amount is not None:
            match = next((a for a in amounts if abs(a - expected_amount) < 0.01), None)
            if match is not None:
                merged["amount"] = match
            else:
                counts = Counter([round(a, 2) for a in amounts])
                top_amt, _ = counts.most_common(1)[0]
                merged["amount"] = top_amt
        else:
            # 2. Majority consensus across passes
            counts = Counter([round(a, 2) for a in amounts])
            top_amt, count = counts.most_common(1)[0]
            if count >= 2 or len(counts) == 1:
                merged["amount"] = top_amt
            elif results[0].get("amount") is not None:
                merged["amount"] = results[0]["amount"]
            else:
                merged["amount"] = top_amt

    # For other fields, take first non-None from any pass
    for field in ["tx_id", "utr", "payee_name", "payee_upi_id", "date_str", "time_str",
                  "app_indicator", "status_text"]:
        if merged.get(field) is None:
            for r in results[1:]:
                if r.get(field) is not None:
                    merged[field] = r[field]
                    break

    # Merge warnings
    all_warnings = []
    seen = set()
    for r in results:
        for w in r.get("warnings", []):
            if w not in seen:
                all_warnings.append(w)
                seen.add(w)
    merged["warnings"] = all_warnings

    # Use max confidence
    merged["ocr_confidence"] = max(
        (r.get("ocr_confidence", 0.0) for r in results), default=0.0
    )

    return merged
