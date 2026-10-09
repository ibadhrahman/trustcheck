# Backend A Progress Handoff

This file contains project state for a future assistant. It intentionally contains no passwords, tokens, or secret keys.

## 1. Current status

- Stage 0 setup and Stage 1 foundation are complete and merged into `main`. Stage 0 was PR #1; Stage 1 was PR #2. The handoff files were also merged into `main` at `d3c85dd`.
- Stage 2 registration, login, JWT creation, and the authentication dependency are implemented in `app/auth.py` and wired into `app/main.py`.
- Next coding stage: Stage 3, certificate photo upload, hash chain, certificate lookup/verification, and ledger status.
- Stage 2 code is committed and pushed, but has not been runtime-tested in this turn. Its PR still needs to be opened and reviewed.
- The current worktree is on `backend-a/stage-2-auth`, based on the pulled `main` at `d3c85dd`.

## 2. Decisions made

- `GET /api/health` returns exactly `{"status":"ok"}`. It is implemented only in `app/main.py`, is a helper outside Shared Contract v2, and uses `include_in_schema=False` so it is absent from Swagger/OpenAPI.
- The SQLite database defaults to `trustcheck.db` in the project root. `TRUSTCHECK_DB_PATH` can override the path for local checks.
- The database uses the internal table name `payment_references` for reference records.
- Analysis stubs return score 50, verdict `careful`, and a warning that no checks were performed. They do not claim that an image, screenshot, or text is genuine.
- FastAPI mounts `frontend/` at `/`; the mount is added after API routes. CORS allows all origins, methods, and headers, with credentials disabled.
- Stage 1 was initially built on `origin/main` at `b355066`; Stage 0 was merged first, followed by Stage 1. Both Stage 0 setup files and Stage 1 app files are now present on `main`.
- JWT signing uses the `TRUSTCHECK_JWT_SECRET` environment variable when provided; otherwise, development uses a fresh random process-local key. Tokens expire after 24 hours. Without the environment variable, tokens stop working after the server restarts.
- Auth responses contain `token` and a public `seller` object with `seller_id`, `name`, `phone`, `shop_name`, and `upi_id`; `password_hash` is never returned.
- Duplicate registration phone numbers return HTTP 409, invalid login returns HTTP 401, and request/framework errors use `{"error":"plain-language message"}`.

## 3. Files Backend A owns and what each does

- `app/main.py` — creates the FastAPI app, configures CORS and static serving, initializes the database, includes the auth router, normalizes API errors, and provides `GET /api/health`.
- `app/db.py` — defines the SQLite tables and indexes and provides `get_connection()` and `init_db()`.
- `app/auth.py` — implements `POST /api/auth/register`, `POST /api/auth/login`, bcrypt password hashing, JWT creation, and `get_current_seller()`.
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
| POST | `/api/auth/register` | Implemented with the contract fields and response shape; no runtime request has been sent in this turn. |
| POST | `/api/auth/login` | Implemented with the contract fields and response shape; no runtime request has been sent in this turn. |

`GET /docs` returned HTTP 200 during Stage 1. After Stage 2, it should list the two auth routes; that updated page has not been checked yet. The helper health route remains hidden from OpenAPI.

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
- Stage 2 auth routes have not been runtime-tested yet. Earlier local checks started Uvicorn, requested `/api/health` and `/docs`, and inspected `/openapi.json`; the temporary database from that manual check was removed afterward.

## 7. Known problems and open questions

- Stage 2 auth routes are implemented but not runtime-tested yet. Run the server and the registration/login requests before merging.
- When `TRUSTCHECK_JWT_SECRET` is unset, the random development signing key changes after a process restart, invalidating previously issued tokens. Configure the environment variable when stable tokens across restarts are needed.
- `app/analysis/__init__.py` is only a stub. Backend B must replace it; Backend A must pull Backend B's change before Stage 5 testing and must not overwrite it.
- Tesseract was not found during the earlier setup check. Backend B owns its installation.
- Never add `trustcheck.db` or `app/__pycache__/` to Git; `.gitignore` now excludes them.
- `tests/test_api.py` and `seed.py` are future-stage work and are not available yet.

## 8. Git state

- Current branch: `backend-a/stage-2-auth`, tracking the pushed branch on `origin`, created from `main` at `d3c85dd`.
- Current last commit message: `Backend A: update Stage 2 handoff Git state`.
- Stage 2 source commit `9c575d4` (`Backend A: stage 2 - register, login, JWT`) is pushed to `origin`.
- Pushed and merged: Stage 0 PR #1 and Stage 1 PR #2. Their implementation commits were `8e88a4d` and `ddd9593` respectively.
- `AGENTS.md` and `BACKEND_A_PROGRESS.md` are merged into `main` at `d3c85dd`.
- Pulled `main` since the last stage: yes. `git checkout main` and `git pull origin main` completed before creating the Stage 2 branch. `requirements.txt` was unchanged.
- Stage 2 PR is not open. The GitHub integration returned HTTP 403 (`Resource not accessible by integration`); open this branch's PR after signing in: `https://github.com/ibadhrahman/trustcheck/pull/new/backend-a/stage-2-auth`.
- No uncommitted or unpushed changes remain after the final handoff-state push.

## 9. Next steps

1. Run the Stage 2 local registration/login checks and open the PR at `https://github.com/ibadhrahman/trustcheck/pull/new/backend-a/stage-2-auth`; merge after a teammate says OK.
2. Before Stage 3, run `git checkout main` and `git pull origin main`. If `requirements.txt` changed, run `pip install -r requirements.txt` and `python check_setup.py` again.
3. Create `backend-a/stage-3-ledger` from the updated `main`; implement photo upload, SHA-256 hashing, the certificate hash chain, certificate lookup/verification, and `/api/ledger/status`.
