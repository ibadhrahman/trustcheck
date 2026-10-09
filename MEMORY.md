# TrustCheck — Build Memory & Progress Tracker
> **Purpose:** This file tracks everything built in TrustCheck. All phases are tracked with exact statuses, design decisions, and testing instructions.

---

## 🧠 Project Identity
- **App Name:** TrustCheck
- **Tagline:** Verify the details. Question the proof. Build digital trust.
- **Type:** Full-stack cybersecurity fraud-prevention platform for small/social sellers
- **Stack:** Python 3.11+ / FastAPI / SQLite / SQLAlchemy | Vanilla HTML+CSS+JS frontend
- **Root path:** `c:\Users\haani\Desktop\opcodev2\`

---

## ✅ COMPLETED WORK (ALL PHASES)

### Phase 1A — Project Foundation
| File | Status | Notes |
|------|--------|-------|
| `.gitignore` | ✅ Done | Covers venv, db, .env, uploads, screenshots |
| `.env.example` | ✅ Done | All env vars with placeholders |
| `.env` | ✅ Done | Local configuration for development |
| `requirements.txt` | ✅ Done | FastAPI, uvicorn, sqlalchemy, passlib, bcrypt, pillow, pytesseract, imagehash, pytest, etc. (compatible with Python 3.13+) |

### Phase 1B — Backend Core
| File | Status | Notes |
|------|--------|-------|
| `app/config.py` | ✅ Done | pydantic-settings, all env vars, CORS, HMAC, upload size |
| `app/db.py` | ✅ Done | SQLAlchemy engine + SessionLocal + `init_db()` |
| `app/models.py` | ✅ Done | ALL 12 ORM models: User, SellerProfile, SellerReferralCode, OrderReferralCode, Product, PhotoCertificate, LedgerEntry, Order, PaymentSubmission, PaymentReference, ScamCheck, AuditEvent |
| `app/schemas.py` | ✅ Done | All Pydantic v2 schemas for requests/responses |
| `app/auth.py` | ✅ Done | bcrypt hashing, JWT creation/decode, `get_current_user` dependency |
| `app/referral_codes.py` | ✅ Done | Code generation (`SL-XXXX-XXXX` + `TC-XXXXXXXX`), uniqueness enforcement, shareable message builder |
| `app/ledger.py` | ✅ Done | Hash-linked append-only ledger + integrity verification |

### Phase 1C — Analysis Modules
| File | Status | Notes |
|------|--------|-------|
| `app/analysis/__init__.py` | ✅ Done | Package init |
| `app/analysis/ocr_check.py` | ✅ Done | Multi-pass OCR (Tesseract + RapidOCR fallback), field extraction for GPay/PhonePe/Paytm/BHIM, preprocessing, conflict merging |
| `app/analysis/forensics.py` | ✅ Done | SHA-256, perceptual hash (`pHash`), EXIF inspection, ELA score |
| `app/analysis/duplicate_detection.py` | ✅ Done | HMAC fingerprints for tx refs, perceptual + exact screenshot duplicate detection |
| `app/analysis/scam_rules.py` | ✅ Done | Rule-based scam/phishing checker with zero-storage policy |

### Phase 2 — Backend API Routes & Main App
| File | Status | Notes |
|------|--------|-------|
| `app/__init__.py` | ✅ Done | Package root |
| `app/routers/__init__.py` | ✅ Done | Routers package |
| `app/routers/auth_router.py` | ✅ Done | POST /api/auth/register, login, GET /api/auth/me |
| `app/routers/seller_router.py` | ✅ Done | GET/PATCH /api/seller/profile, GET /api/seller/referral-code |
| `app/routers/products_router.py` | ✅ Done | CRUD products, certificate upload, reverse verification, ledger status |
| `app/routers/orders_router.py` | ✅ Done | Create/list/get orders, cancel, referral code detail |
| `app/routers/payments_router.py` | ✅ Done | Analyze screenshot, cross-verify, history, confirm payment |
| `app/routers/scam_router.py` | ✅ Done | POST /api/scam-check (stores minimal length/score only) |
| `app/routers/dashboard_router.py` | ✅ Done | Real database statistics + audit log activity |
| `app/main.py` | ✅ Done | FastAPI application wiring, CORS, startup init, health check, static file mounting |

### Phase 3 — Frontend (10 Pages & Assets)
| File | Status | Notes |
|------|--------|-------|
| `frontend/css/styles.css` | ✅ Done | Modern dark cybersecurity design system (28KB+), typography, responsive layout |
| `frontend/js/api.js` | ✅ Done | Central fetch wrapper, JWT bearer injection, toast notifications, auth helpers |
| `frontend/index.html` | ✅ Done | Public landing page with features, how-it-works, honest limits |
| `frontend/login.html` | ✅ Done | Sign in page with error handling and redirect support |
| `frontend/register.html` | ✅ Done | Seller registration with profile fields and validation |
| `frontend/dashboard.html` + `dashboard.js` | ✅ Done | Live stats cards, quick action links, recent audit activity feed |
| `frontend/orders.html` + `orders.js` | ✅ Done | Order creation, referral code display, copy snippet, search and filter |
| `frontend/verify-payment.html` + `verify-payment.js` | ✅ Done | Payment cross-verification, drag-and-drop OCR, side-by-side comparison |
| `frontend/products.html` + `products.js` | ✅ Done | Products catalogue, photo certificate upload, ledger status indicator, reverse image check |
| `frontend/scam-checker.html` + `scam-checker.js` | ✅ Done | Heuristic scam analyzer, 4 quick demo presets, threat score dial, safe next steps |
| `frontend/profile.html` + `profile.js` | ✅ Done | Seller settings, registered UPI ID, permanent `SL-XXXX-XXXX` bio snippet |

### Phase 6 — Buyer Experience & RapidOCR Engine
| File | Status | Notes |
|------|--------|-------|
| `rapidocr-onnxruntime` | ✅ Installed | Bundled ONNX runtime OCR fallback to extract fields without system Tesseract binary dependencies |
| `frontend/verify.html` | ✅ Done | Public, frictionless buyer upload portal requiring NO login or account |
| `app/auth.py` | ✅ Done | Added `get_optional_current_user` for public/authenticated dual-mode endpoints |
| `app/routers/payments_router.py` | ✅ Done | Publicly accessible cross-verify & analyze endpoints; automatic attribution via seller code or order code |
| `app/referral_codes.py` | ✅ Done | Added `resolve_seller_referral_code` and case-insensitive resolution for permanent `SL-XXXX-XXXX` codes |
| `tests/test_payment_analysis.py` | ✅ Done | Added unit tests for public buyer uploads with order code and permanent seller code |

### Phase 7 — UPI OCR Robustness & Extraction Heuristics
| File | Status | Notes |
|------|--------|-------|
| `app/analysis/ocr_check.py` | ✅ Enhanced | Fixed RapidOCR rupee symbol recognition (`\u56de`, `?`, `0`), standalone decimal & integer lines, and Indian UPI layouts (GPay, PhonePe, Paytm, BHIM). Implemented consensus voting across multi-pass OCR to eliminate conflict wipes. |
| `app/routers/payments_router.py` | ✅ Updated | Passes `expected_amount` and `expected_payee_name` from order/seller context to corroborate OCR extractions without guessing. |
| `tests/test_payment_analysis.py` | ✅ Updated | Added unit test coverage for PhonePe, GPay, and Paytm screenshot text extractions (27/27 tests passing). |

### Phase 8 — Unique Verification Transaction ID & Proof Sharing
| File | Status | Notes |
|------|--------|-------|
| `app/referral_codes.py` | ✅ Done | Added `generate_verification_tx_id()` (`TXN-XXXX-XXXX`) and `build_buyer_confirmation_message()` |
| `app/models.py` | ✅ Done | Added `verification_tx_id` indexed column to `PaymentSubmission` |
| `app/schemas.py` | ✅ Done | Included `verification_tx_id` in `CrossVerifyResult` and compatibility aliases |
| `app/routers/payments_router.py` | ✅ Done | Auto-generates unique `verification_tx_id` on every analyzed image and returns it in response & history |
| `frontend/verify.html` | ✅ Enhanced | Prominent Transaction Verification ID card with one-click **"📋 Copy ID"** and **"💬 Share with Seller"** (WhatsApp integration) |
| `frontend/verify-payment.html` + `.js` | ✅ Enhanced | Verification ID card and history table column for seller tracking |

### Phase 9 — Module Import Resolution & Frontend Design System
| File | Status | Notes |
|------|--------|-------|
| `.vscode/settings.json` | ✅ Created | Configured default python interpreter to `${workspaceFolder}/.venv/Scripts/python.exe` and added extraPaths. |
| Python Environment | ✅ Synced | Installed missing packages (`passlib`, `bcrypt`, `sqlalchemy`, `pillow`, etc.) into global Python 3.13 to ensure zero import errors in any editor mode. |
| `app/analysis/` & `app/routers/` | ✅ Cleaned | Fixed all type-checker edge cases for PIL and null hash distances. Pyright reports 0 errors, 0 warnings. |
| `frontend/css/styles.css` | ✅ Updated | Adopted Deep Midnight Navy & Lavender projector FinTech styling system (`--ink: #111827`, `--bg: #EAE7F0`, fluid gradient flow keyframe, high-contrast hairline borders). |
| `frontend/index.html` | ✅ Enhanced | Redesigned landing page with fluid animated gradient header, brand-mark `✓`, Floating Verified Token Card, and minimal footer strip. |
| `frontend/verify.html` | ✅ Enhanced | Styled buyer payment proof submission card and verification receipt with the same sleek aesthetic. |

### Phase 10 — Multimodal Vision Engine Foundation
| File | Status | Notes |
|------|--------|-------|
| `app/analysis/gemini_vision.py` | ✅ Archived | Gemini multimodal module retained as optional fallback. |

### Phase 11 — DeepSeek V4.1 Flash Integration & Scam Checker Removal
| File | Status | Notes |
|------|--------|-------|
| `requirements.txt` | ✅ Updated | Added `openai>=1.0.0` for OpenAI-compatible async multimodal completions. |
| `app/config.py` | ✅ Updated | Added `deepseek_api_key`, `deepseek_base_url` (`https://api.deepseek.com`), `deepseek_model` (`deepseek-v4.1-flash`), `deepseek_enabled`, `deepseek_timeout_seconds`, and `deepseek_max_retries`. |
| `.env.example` & `.env` | ✅ Updated | Documented DeepSeek V4.1 Flash configuration and credentials. |
| `app/analysis/deepseek_vision.py` | ✅ Created | DeepSeek multimodal vision module: `AsyncOpenAI` client lifecycle, in-memory image downscaling (max 1280px) and base64 encoding (`data:image/jpeg;base64`), structured JSON schema (`DeepSeekPaymentExtraction`), strict Indian UPI amount reading rules (distinguishes ₹210 vs ₹10, no digit dropping), field confidence and uncertain flags. |
| `app/analysis/payment_extractor.py` | ✅ Updated | Routes to DeepSeek V4.1 Flash as primary multimodal engine; falls back cleanly to local multi-pass OCR if unconfigured or error occurs. |
| `app/analysis/ocr_check.py` | ✅ Updated | Updated `get_ocr_availability()` to report `deepseek` status on `/api/health`. |
| `tests/test_deepseek_vision.py` | ✅ Created | 8 unit and integration tests covering schema validation, PhonePe ₹10, BHIM ₹1, amount distinction (₹210 vs ₹10, ₹1000, decimals), missing amounts, API timeout/quota fallbacks, and full `/api/payments/cross-verify` API flow. (31/31 tests passing). |
| Scam Checker Removal | ✅ Complete | Removed `scam_router` from `app/main.py`; removed Scam Checker nav items from `dashboard.html`, `orders.html`, `verify-payment.html`, `products.html`, `profile.html`; updated `index.html` landing page features; purged `frontend/scam-checker.html` and `scam-checker.js`. |

---

## 🔑 KEY DESIGN DECISIONS (PRESERVED)

### 1. Referral Code Format & Persistence
- **Seller code:** `SL-XXXX-XXXX` (permanent bio identifier that NEVER changes across transactions; uniquely identifies seller)
- **Order code:** `TC-XXXXXXXX` (order-specific reference for structured reconciliation)
- Alphabet excludes ambiguous characters (`0`, `O`, `1`, `I`).
- No QR codes are used to eliminate QR redirection and tampering vulnerabilities.
- **Zero-Friction Public Buyer Flow:** Buyers do not need to register or log in. They simply visit `/verify.html`, input the seller's permanent code or an order reference, upload their payment receipt, and TrustCheck cross-verifies the transaction against registered seller details.

### 2. Standardized Risk Result Format
```json
{
  "score": 0,
  "verdict": "genuine | careful | suspicious",
  "reasons": [{"level": "ok | warning | error", "text": "..."}],
  "details": {},
  "heatmap_png_base64": null,
  "disclaimer": "Risk estimate only — not proof of payment."
}
```

### 3. Absolute Invariants
1. Never guess or substitute an unreadable amount.
2. Never mark an order paid solely because referral code is valid.
3. Never claim bank credit is confirmed without actual banking app verification.
4. Process payment screenshots in-memory only — never write raw payment images to disk.
5. Store HMAC-SHA256 fingerprints of transaction references for deduplication.
6. Enforce strict seller multi-tenant isolation across all endpoints.
7. Buyers can submit payment verification without signing in.

---

## 🚀 How to Run the App
```bash
# 1. Activate virtual environment
.\.venv\Scripts\activate

# 2. Seed demo data
python scripts/seed_demo.py

# 3. Run server
uvicorn app.main:app --reload --port 8000
```
Open **http://localhost:8000** in your browser:
- Public Landing Page: [http://localhost:8000](http://localhost:8000)
- Public Buyer Verification (No Sign-in needed): [http://localhost:8000/verify.html](http://localhost:8000/verify.html)
- Seller Login: [http://localhost:8000/login.html](http://localhost:8000/login.html) (`seller@artisan.in` / `Password123!`)
- Test Suite: `.\.venv\Scripts\pytest -p no:cacheprovider tests/ -v` (26 passing tests)

