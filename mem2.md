# TrustCheck handoff memory

## Active request
Continue the buyer order-outcome and seller-resolution feature in `C:\Users\haani\Desktop\opcodev2`. The user explicitly chose **no buyer signup or login**: buyers use the private order reference/link shared by their seller to view order status and report an issue. Keep payment verification unchanged. Do not deploy or publish.

## Security and access
- FastAPI + SQLAlchemy; SQLite locally, Supabase PostgreSQL when configured. Vanilla HTML/CSS/JS frontend served by FastAPI.
- Follow repo `AGENTS.md`: tenant-filter seller queries, don't reveal order data through guessable IDs, keep payment screenshots in memory, keep Supabase tables private.
- A normal numeric order ID or public `TC-...` referral code is not a buyer credential and lookup with those returns 404. Buyer lookup uses the clean, human-readable reference format `TXN-XXXX-XXXX` (e.g. `TXN-PCFY-4A5K`) or payment verification ID shared by the buyer. Only its HMAC is stored in `orders.buyer_access_hmac`; plaintext is returned to seller only on order creation or allowed rotation. The buyer can paste the raw reference `TXN-...`, full link `http://.../buyer.html#claim=TXN-...`, or open the link directly.
- Buyer report text/history is shown only to someone with that order's private reference and to the owning authenticated seller. Private product/report images are validated, normalized with EXIF removed, stored outside static hosting, and returned only via ownership-checked endpoints. Payment screenshots remain in-memory only.

## Buyer and seller flow
- `frontend/buyer.html` is a no-login order lookup page. It shows the order status and, after seller confirms bank credit, offers “Received as described” or an issue report: not received, wrong item, damaged item, missing item, or not as described.
- Positive confirmation (optional photo) does not create a seller issue. One outcome per order is enforced; a positive confirmation may later be converted into one problem report. Duplicate problem submissions are rejected.
- The seller sees issue reports in their authenticated Orders/outcomes page and gets an in-app activity entry. Seller can offer replacement/refund/other; only the buyer can confirm resolution. History is append-only.
- Sellers can rotate references before an issue is filed. Rotation is blocked once a problem is reported so the seller cannot cut off the buyer's access to the report/history.
- Future buyers receive a neutral warning when the configured number of unresolved reports pass their response deadline. Defaults: response period 48 hours, threshold 3, rolling window 30 days; threshold is configurable to 2 or 3. Without buyer accounts, TrustCheck can count distinct orders but cannot prove reports came from distinct people. Do not describe that as verified distinct-buyer counting.

## Database
- `OrderOutcome.buyer_id` and `buyer_received_at` are nullable for anonymous buyers. Buyer auth routes/dependency are removed. `BuyerAccount` model/table and nullable legacy ID references remain only for compatibility with earlier development schema.
- SQLite startup rebuilds the old `order_outcomes` table to make the fields nullable while preserving existing rows and references. Verified on `trustcheck_local.db`: both fields are nullable and `PRAGMA foreign_key_check` is clean.
- Supabase migrations: `supabase/migrations/20261010022355_buyer_order_outcomes.sql` and `supabase/migrations/20261010150000_buyer_order_reference_access.sql`. They have **not** been applied to hosted Supabase. Do not apply unless the user explicitly requests deployment/migration.
- Do not change `.env` secrets. Previously, `.env` Supabase DB auth failed. Local server is running with a process-only SQLite override.

## Relevant files
- API/data: `app/routers/outcomes_router.py`, `app/outcome_utils.py`, `app/models.py`, `app/schemas.py`, `app/db.py`, `app/auth.py`, `app/routers/orders_router.py`
- UI: `frontend/buyer.html`, `frontend/js/buyer-orders.js`, `frontend/orders.html`, `frontend/js/orders.js`, `frontend/verify.html`, `frontend/index.html`
- DB: `supabase/migrations/20261010022355_buyer_order_outcomes.sql`, `supabase/migrations/20261010150000_buyer_order_reference_access.sql`
- Tests: `tests/test_order_outcomes.py`
- Handoff: `mem2.md`

## Local run and verification
- Local server is up at `http://127.0.0.1:8001/`; buyer page `http://127.0.0.1:8001/buyer.html` is open in the browser. `/`, `/buyer.html`, and `/js/buyer-orders.js` returned 200. This is a fresh local SQLite DB and has no hosted Supabase orders; create/use an order in the local seller account to test the buyer link.
- Full test suite: `53 passed` (276 legacy deprecation warnings), using process-only `DATABASE_URL=sqlite:///./trustcheck_test_startup.db`.
- `node --check frontend/js/buyer-orders.js` and `frontend/js/orders.js`, Python `compileall`, and `git diff --check` passed.

## Final user-facing summary
Describe the no-account private reference flow, seller resolution flow, touched files, test result, Supabase migration step, and distinct-buyer-counting limitation. Use absolute paths for file links.
