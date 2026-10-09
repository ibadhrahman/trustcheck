# Backend A Progress Handoff

This file contains project state for a future assistant. It intentionally contains no passwords, tokens, or secret keys.

## 1. Current status

- Stage 0 setup and Stage 1 foundation are complete and merged into `main`. Stage 0 was PR #1; Stage 1 was PR #2.
- Stage 1 provides the FastAPI shell, SQLite schema, static frontend mount, CORS, hidden helper health route, and temporary analysis stubs.
- Next coding stage: Stage 2, seller registration, login, JWT, and the authentication dependency.
- No coding stage is half-finished. This handoff update (`AGENTS.md` and `BACKEND_A_PROGRESS.md`) is currently uncommitted.
- The current worktree is on `main` at merge commit `daabddf`; it matches `origin/main`.

## 2. Decisions made

- `GET /api/health` returns exactly `{"status":"ok"}`. It is implemented only in `app/main.py`, is a helper outside Shared Contract v2, and uses `include_in_schema=False` so it is absent from Swagger/OpenAPI.
- The SQLite database defaults to `trustcheck.db` in the project root. `TRUSTCHECK_DB_PATH` can override the path for local checks.
- The database uses the internal table name `payment_references` for reference records.
- Analysis stubs return score 50, verdict `careful`, and a warning that no checks were performed. They do not claim that an image, screenshot, or text is genuine.
- FastAPI mounts `frontend/` at `/`; the mount is added after API routes. CORS allows all origins, methods, and headers, with credentials disabled.
- Stage 1 was initially built on `origin/main` at `b355066`; Stage 0 was merged first, followed by Stage 1. Both Stage 0 setup files and Stage 1 app files are now present on `main`.

## 3. Files Backend A owns and what each does

- `app/main.py` — creates the FastAPI app, configures CORS and static serving, initializes the database, and provides `GET /api/health`.
- `app/db.py` — defines the SQLite tables and indexes and provides `get_connection()` and `init_db()`.
- `app/auth.py` — planned seller registration/login routes, JWT creation, and authentication dependency; not created yet.
- `app/ledger.py` — planned certificate photo upload, SHA-256 hash chain, certificate lookup/verification, and ledger status; not created yet.
- `app/orders.py` — planned seller order routes and public buyer order view; not created yet.
- `app/references.py` — planned payment-proof handling, reference lookup/confirmation, reuse checks, and reference rate limiting; not created yet.
- `app/qr.py` — planned QR image generation for buyer order links; not created yet.
- `app/analysis/__init__.py` — temporary contract-shaped stubs for `analyze_payment_screenshot`, `analyze_image`, `check_scam_text`, and `phash`; Backend B replaces it after the stub commit.
- `seed.py` — planned idempotent demo data and Pillow placeholder images; not created yet.
- `requirements.txt` — Stage 0 dependency list; merged into `main` in PR #1.
- `.gitignore` — Stage 0 ignore rules; merged into `main` in PR #1.
- `check_setup.py` — Stage 0 package/Tesseract checker; merged into `main` in PR #1.
- `tests/test_api.py` — planned endpoint and common-error coverage for Stage 7; not created yet.
- `BACKEND_A_PROGRESS.md` — this handoff file; update it at the end of every stage before giving Git commands.

## 4. Endpoints working now

| Method | Path | Result and check |
| --- | --- | --- |
| GET | `/api/health` | Returns `{"status":"ok"}`. Checked locally with PowerShell against Uvicorn on port 8001; HTTP 200. Hidden from OpenAPI by design. |

`GET /docs` also returned HTTP 200 and Swagger UI loaded. It currently shows no operations because no Shared Contract v2 endpoints have been implemented yet and the helper route is hidden from the schema.

## 5. Database

The current schema creates these tables:

| Table | Columns |
| --- | --- |
| `sellers` | `seller_id`, `name`, `phone`, `shop_name`, `upi_id`, `password_hash`, `created_at` |
| `certificates` | `cert_id`, `seller_id`, `title`, `sha256`, `image_path`, `photo_url`, `created_at`, `prev_hash`, `link_hash` |
| `orders` | `order_id`, `seller_id`, `photo_id`, `product_name`, `price`, `status`, `link`, `created_at`, `reference_id` |
| `payment_references` | `reference_id`, `order_id`, `seller_id`, `status`, `screenshot_sha256`, `txn_id`, `screenshot_path`, `analysis_json`, `submitted_at`, `expires_at` |
| `override_logs` | `log_id`, `reference_id`, `seller_id`, `action`, `logged_at` |

Indexes exist for certificate/order seller lookups, order creation time, reference order/seller lookups, screenshot SHA-256, and transaction ID.

## 6. Commands

Run these from the repository root. Stage 0 is merged into `main`, so `requirements.txt` is available.

**Windows PowerShell:**

```powershell
python --version
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python check_setup.py
python -m uvicorn app.main:app --reload
```

**Mac:**

```bash
python3 --version
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python check_setup.py
python -m uvicorn app.main:app --reload
```

- Tests: Stage 7 has not created `tests/test_api.py`. Planned command: `python -m unittest discover -s tests`; confirm it when Stage 7 chooses and implements the test runner. There is no test suite to run yet.
- Seed data: Stage 6 has not created `seed.py`. The planned command is `python seed.py` after that file exists.
- Local checks completed so far: start Uvicorn, request `/api/health`, request `/docs`, and inspect `/openapi.json`. The temporary database used for the manual check was removed afterward.

## 7. Known problems and open questions

- The Stage 1 branch has no contract endpoints yet. Swagger showing no operations is expected until later stages.
- `app/analysis/__init__.py` is only a stub. Backend B must replace it; Backend A must pull Backend B's change before Stage 5 testing and must not overwrite it.
- Tesseract was not found during the earlier setup check. Backend B owns its installation.
- Never add `trustcheck.db` or `app/__pycache__/` to Git; `.gitignore` now excludes them.
- `tests/test_api.py` and `seed.py` are future-stage work and are not available yet.

## 8. Git state

- Current branch: `main`, matching `origin/main`.
- Current last commit: `daabddf` — `Merge pull request #2 from ibadhrahman/backend-a/stage-1-foundation`.
- Pushed and merged: Stage 0 PR #1 and Stage 1 PR #2. Their implementation commits were `8e88a4d` and `ddd9593` respectively.
- Pulled `main` since the last stage: no pull was run during this handoff update. At inspection time, local `main` already matched `origin/main` at `daabddf`; whether Backend A ran a pull command after the last stage cannot be verified from the worktree.
- Not yet pushed: this `AGENTS.md` and `BACKEND_A_PROGRESS.md` update.
- The only untracked files at the last status check were `AGENTS.md` and `BACKEND_A_PROGRESS.md`.

## 9. Next steps

1. Before Stage 2, run `git checkout main` and `git pull origin main`. If `requirements.txt` changed, run `pip install -r requirements.txt` and `python check_setup.py` again.
2. Create `backend-a/stage-2-auth` from the updated `main`.
3. Implement seller registration, login, JWT creation, and the authentication dependency in `app/auth.py`, then expose only the contract routes in `app/main.py`.
