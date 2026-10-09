# AGENTS.md — Development Guidelines & Architectural Invariants

This file defines guidelines and behavioral constraints for any autonomous or assistant agent working on the **TrustCheck** codebase.

---

## 🏛️ Architecture & System Design

TrustCheck is an opinionated, defense-oriented cybersecurity fraud prevention MVP for social commerce merchants.

### Core Technology Stack
- **Backend:** Python 3.10+ / FastAPI / SQLAlchemy 2.0 / Pydantic v2 / SQLite
- **Frontend:** Vanilla HTML5, CSS3, JavaScript (no external build systems, no Tailwind, no node_modules required). Served directly by FastAPI via Starlette `StaticFiles`.
- **Database:** SQLite (`trustcheck.db`) with relational schema and tenant isolation enforced via `seller_id` on every query.

---

## 🔒 Security & Privacy Invariants (CRITICAL — NEVER VIOLATE)

1. **Zero-Storage for Payment Proofs:**
   - NEVER persist raw uploaded payment screenshot images to disk, object storage, or SQLite BLOBs.
   - All image forensics and OCR checks MUST execute entirely in-memory (`io.BytesIO`).
   - Store only derived mathematical features: SHA-256 digest, perceptual hash (`pHash`), image dimensions, and extracted fields.

2. **Zero-Storage for Scam Message Content:**
   - When users submit text to `/api/scam-check`, NEVER store the raw message text in the database.
   - Only log the content length (`content_length`), detected pattern names, and the risk score.

3. **HMAC Fingerprinting for Transaction References:**
   - Never store raw transaction IDs directly as plaintext keys for deduplication.
   - Use `_hmac_fingerprint()` salted with `settings.hmac_secret` to store and query transaction references in the `PaymentReference` table.

4. **Multi-Tenant Ownership Enforcement:**
   - NEVER allow cross-seller data leakage.
   - Every lookup for an order, product, payment submission, or referral code MUST filter by `current_user.id` or verify `order.seller_id == current_user.id`.
   - Never trust IDs provided by frontend forms without verifying ownership.

5. **No QR Codes:**
   - Do NOT introduce QR code generators or scanners for payment or referral workflows. TrustCheck explicitly relies on human-readable, unambiguous alphanumeric codes (`SL-XXXX-XXXX` and `TC-XXXXXXXX`).

6. **Honest Limitations & Disclaimers:**
   - All risk responses MUST contain the disclaimer: `"Risk estimate only — not proof of payment."`
   - NEVER claim that an order is paid or confirmed simply because a screenshot looks authentic or a referral code matches. Only the seller can confirm bank receipt.

---

## 📁 Repository Structure

```
├── app/
│   ├── config.py                 # Pydantic BaseSettings configuration
│   ├── db.py                     # SQLAlchemy session & Base
│   ├── models.py                 # All 12 ORM models
│   ├── schemas.py                # Pydantic v2 schemas
│   ├── auth.py                   # JWT creation, decode & password hashing
│   ├── ledger.py                 # Hash-linked append-only audit ledger
│   ├── referral_codes.py         # Code generators (SL-XXXX-XXXX, TC-XXXXXXXX)
│   ├── main.py                   # FastAPI entrypoint, router includes, static mount
│   ├── analysis/
│   │   ├── ocr_check.py          # Tesseract/RapidOCR multi-pass extraction
│   │   ├── forensics.py          # ELA score, SHA-256, pHash, EXIF
│   │   ├── duplicate_detection.py# HMAC tx fingerprints & visual deduplication
│   │   └── scam_rules.py         # Deterministic heuristic pattern rules
│   └── routers/
│       ├── auth_router.py        # /api/auth/register, login, me
│       ├── seller_router.py      # /api/seller/profile, referral-code
│       ├── products_router.py    # /api/products, certificates, ledger/status
│       ├── orders_router.py      # /api/orders, referral code resolution, cancel
│       ├── payments_router.py    # /api/payments/analyze, cross-verify, history
│       ├── scam_router.py        # /api/scam-check
│       └── dashboard_router.py   # /api/dashboard/stats, activity
├── frontend/
│   ├── css/styles.css            # Dark cybersecurity design system
│   ├── js/api.js                 # Central fetch wrapper, auth helpers, toasts
│   ├── index.html                # Public landing page
│   ├── login.html & register.html# Auth pages
│   ├── dashboard.html            # Analytics & recent activity
│   ├── orders.html               # Orders & referral code generation
│   ├── verify-payment.html       # Payment cross-verification tool
│   ├── products.html             # Products & photo certification
│   ├── scam-checker.html         # Heuristic scam checker
│   └── profile.html              # Seller business info & bio code
├── tests/                        # Pytest suite with in-memory SQLite fixtures
├── scripts/                      # Setup scripts (PowerShell & Bash) and seeder
├── requirements.txt              # Pinned/flexible Python dependencies
└── MEMORY.md                     # Build progress tracker
```

---

## 🧪 Testing Guidelines

- Always run tests after making modifications:
  ```bash
  .\.venv\Scripts\pytest tests/ -v
  ```
- Use `tests/conftest.py` in-memory SQLite fixtures (`db_session`, `client`, `test_user`, `auth_headers`).
- Every new router endpoint must have corresponding test coverage verifying:
  1. Success path
  2. Unauthenticated access rejection (401)
  3. Multi-tenant access violation rejection (404/403)
