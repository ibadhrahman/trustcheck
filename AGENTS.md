# TrustCheck Backend A Instructions

## Files I own

- `app/main.py` — FastAPI app, CORS, frontend static serving, startup, and the helper health route.
- `app/db.py` — SQLite schema, connection handling, and database initialization.
- `app/auth.py` — seller registration and login routes, JWT creation, and seller authentication dependency.
- `app/ledger.py` — certificate photo upload, hash chain, public certificate lookup and verification, and ledger status.
- `app/orders.py` — seller order routes and the public buyer order view.
- `app/references.py` — payment proof, reference lookup and confirmation, reuse checks, and reference rate limiting.
- `app/qr.py` — QR code generation for buyer order links.
- `app/analysis/__init__.py` — Backend A's one-time analysis stubs; after that stub commit, Backend B owns and replaces this file.
- `seed.py` — idempotent demo seller, products, orders, references, and placeholder images.
- `requirements.txt` — the project's exact Python dependency list.
- `.gitignore` — excludes virtual environments, caches, databases, uploads, and secrets.
- `check_setup.py` — checks Python package imports, the bcrypt pin, and whether Tesseract is available.
- `tests/test_api.py` — API endpoint and common-error coverage when Stage 7 is implemented.
- `BACKEND_A_PROGRESS.md` — current-stage handoff, decisions, tested endpoints, Git state, and next steps.

Do not commit or edit `app/analysis/*` after the one-time stub commit, `frontend/*`, or `tests/sample_images/*`. Those files belong to teammates. After a pull, changes in those paths are expected; never overwrite, revert, or edit them.

## Git rules

- The team shares one GitHub repository and uses `main` as the integration branch.
- Use one short-lived `backend-a/stage-N-...` branch per stage. Open a pull request and merge after a teammate says OK. Do not leave a branch open for more than a few hours.
- Never commit the virtual environment, database files, uploaded images, or secrets. Never use `git add .`, `git add -A`, or `git push --force`.
- At each stage, add only the Backend A files for that stage, inspect `git status`, commit with a stage-specific message, and push the branch.
- After a pull request is merged, update local `main` before starting the next branch.
- Remind Backend A to tell the team what was pushed and which endpoints work.
- For a merge conflict in a teammate's file, do not overwrite it; ask Backend A to message that teammate. For a conflict in Backend A's file, provide the full corrected file.

### Sync rules

1. Before each stage, remind Backend A to run `git checkout main` and `git pull origin main`. If `requirements.txt` changed, remind Backend A to run `pip install -r requirements.txt` and `python check_setup.py` again.
2. After a pull request is merged, remind Backend A to run `git checkout main` and `git pull origin main` before starting the next branch.
3. Before pushing, include `git pull --rebase origin main` on the stage branch in the Git commands.
4. When a teammate announces a push Backend A needs, tell Backend A to pull first. In particular, when Backend B replaces the stubs in `app/analysis/__init__.py`, remind Backend A to pull before testing Stage 5.
5. Never pull while editing files. Finish and commit the current stage first.
6. After a pull, changes to `app/analysis/*`, `frontend/*`, and `tests/sample_images/*` are expected. Never edit, revert, or overwrite them.
7. Keep branches short-lived: one branch per stage, merged into `main` as soon as a teammate says OK. No branch should stay open for more than a few hours.
8. For merge conflicts, keep the existing conflict rule: a teammate's file means Backend A messages that teammate; a Backend A file means provide the full corrected file.

## End of every stage checklist

- List files created or changed.
- Give exact Windows and Mac commands to run.
- Describe the expected correct output.
- List likely errors and fixes.
- Give stage-specific Git commands and remind Backend A to open a pull request.
- Remind Backend A to tell the team what was pushed and which endpoints work.
- Update `BACKEND_A_PROGRESS.md` with the Git state, including whether I have pulled `main` since the last stage.
