---
title: RBAC Authorization Implemented — Uncommitted on feature/rbac-authorization
date: 2026-09-25
type: session-handoff
area: authorization
status: in-progress
session_id: e4ce8334-7603-4da1-bb94-f1b2180e6010
tags: [authorization, rbac, pgvector, hybrid-search, chunking, logging, backend, frontend, docker]
keywords: [feature/rbac-authorization, feature/rag-guardrails, X-User-Id, v_user_accessible_chunks, authz_seeded_grants, rag_documents_dedup_key, RetrievalState, AUTH_DEV_MODE, ADMIN_USERNAME, get_document_unscoped]
supersedes: 09252026/01_handoff-hybrid-search-embedding-fix-merge-gap.md
related: [09252026/02_rbac-authorization-design.md]
next_action: Review the diff and commit it on feature/rbac-authorization, then open a PR — but first merge feature/rag-guardrails into master (still-open item from the previous handoff), because this branch sits on top of it.
---

## TL;DR
- **What:** role-based authorization is fully implemented and verified, but **not committed**.
  - 4 roles and 4 classifications, with a role→classification access table.
  - Permission views in Postgres, and an `auth/` package that seeds the admin from env plus demo users.
  - Upload takes a classification and tags; dedup is on (classification, hash, creator).
  - Q&A-aware chunking, and permission-scoped hybrid search carried in a `RetrievalState`.
  - Every log line tagged with request id, user and role; `/logs` scoped to the caller.
  - A UI "Acting as" role picker.
- **Why:** the user asked for authorization with a test-friendly role picker, database-enforced document access, and monitorable logs for every step.
- **Where:**
  - The branch is `feature/rbac-authorization`, cut from `feature/rag-guardrails` @ `2511a55`. It holds 56 changed or new files, all uncommitted.
  - The design doc is `09252026/02_rbac-authorization-design.md`.
- **Impact:**
  - 135/135 backend tests pass; ruff and mypy are clean; the frontend `tsc -b` and `vite build` pass.
  - The live Docker stack runs the new code, and the database has been migrated (the migration is additive).

## Current Status

| Check | Command (from `backend/` unless noted) | Result |
|---|---|---|
| Tests | `.venv\Scripts\python -m pytest -q` | **135 passed** (was 84) |
| Lint | `.venv\Scripts\ruff check src tests` | All checks passed |
| Format | `.venv\Scripts\black --target-version py312 --check src tests` | 118 files unchanged |
| Types | `.venv\Scripts\mypy src` | no issues in 75 files |
| Frontend (from `frontend/`) | `npx tsc -b && npx vite build` | built, no type errors |
| Live stack | backend and frontend containers rebuilt with `--force-recreate` | health 200, frontend 200 |
| Live authorization scenario | scratch script (reproduce with the steps in doc 02 §Verification) | every expectation held (see below) |

**Git state:**
- Branch `feature/rbac-authorization` has no commits of its own yet. HEAD is `2511a55`, the same as `feature/rag-guardrails`.
- `git status` shows 56 entries: modified backend, frontend, test and `.env.example` files, plus new files under `auth/` and `tests/auth/` and the two new docs.

## COMPLETED

**Backend** (`backend/src/rag_backend/`):
- **Config:** `config.py` has the `auth_*` / `admin_*` / `seed_documents_classification` settings, plus a validator that fails startup on an inconsistent matrix.
- **Schema:** `db/authz_schema.py` creates:
  - tables `roles`, `users`, `document_classifications`, `role_classification_access` and `authz_seeded_grants`
  - `rag_documents.classification`, `created_by` and `content_hash`
  - the views `v_user_accessible_documents` and `v_user_accessible_chunks`
  - a backfill, then `NOT NULL`, then the unique dedup index
- **Store:** in `db/postgres_store.py`, every user-facing read takes a required `user_id` and queries the views. `find_existing` replaced `find_by_hash`; `update_document_metadata` and `get_document_unscoped` are new.
- **`auth/` package:**
  - `models.py`: `CurrentUser`, `UserRecord`
  - `repository.py`: SQL
  - `service.py`: rules and `AUTH` audit logs
  - `seed.py`: admin from env, demo users, config sync
  - `dependencies.py`: `get_current_user` via `X-User-Id`, `require_admin`
- **API:**
  - `api/routes_auth.py`: `/auth/demo-users`, `/auth/me`, `/auth/classifications`, and admin-only `/auth/users`, `/auth/users/{id}/role`, `/auth/users/{id}/active`, `/auth/access`.
  - `api/routes_upload.py`: classification and tags form fields, the new dedup, `GET /documents/{id}`, and DELETE (creator or admin; 404 when not readable).
  - `api/routes_logs.py`: per-owner visibility. `/eval/run` is now admin only.
- **Indexing:**
  - `rag_pipeline/indexing/frontmatter.py` is new.
  - step2 parses frontmatter.
  - step3 picks `qanda` / `section` / `window` chunking.
  - step5 and step8 store `chunk_strategy`, `section_heading` and `question_id`.
  - `pipeline.py` logs ownership and strategy and stores the frontmatter metadata.
- **Retrieval:**
  - `rag_pipeline/retrieval/state.py` is new.
  - Step 4 is permission-scoped in SQL, step 5 is a defence-in-depth clearance filter, and step 7 uses scoped citations.
  - The pipeline logs the user and state.
  - `eval/runner.py` runs as the calling admin.
- **Observability:**
  - `request_context.py` holds the contextvars and log filter.
  - `logging_config.py` uses the new format.
  - `main.py` adds the startup order, the `X-Request-ID` middleware and the `AuthError` → HTTP status mapping.

**Frontend** (`frontend/src/`):
- `auth/identity.ts`
- `components/RoleSelector.tsx`, wired into `App.tsx`; pages re-key per user
- `api/client.ts`: `apiFetch` with the auth header and readable 401/403 errors
- `api/streaming.ts`: sends the header
- `DocumentUpload.tsx`: classification and tags controls
- `DocumentList.tsx`: classification, tags and creator columns; delete shown only when `can_delete`
- `LogsPage.tsx`: username
- `index.css`

**Tests:**
- New: `tests/auth/{test_dependencies,test_service,test_seed}.py`, `tests/test_routes_permissions.py` and `tests/rag_pipeline/retrieval/conftest.py`.
- Existing tests updated for the new signatures.
- `dummy_store.py` mirrors the views and the auth repository.

**Also closed from the previous handoff:**
- **Item 3, the mypy `Literal` error in `step7_combine_context._assess_evidence`:** fixed.
- **Item 4, route tests hitting real Postgres:** fixed. `main.py` now calls `db_session.init_pool()` through the module, so the conftest patch applies.

**Docs:**
- `09252026/02_rbac-authorization-design.md`
- `.env.example` has a new `# --- Authorization ---` section.

## NOT DONE / STILL OPEN

1. **Nothing is committed.** All work is in the working tree of `feature/rbac-authorization` (see NEXT ACTION).
2. **Hybrid search + embedding fix are still not in `master`.** This was the previous handoff's NEXT ACTION and it was not done this session. `feature/rbac-authorization` is stacked on `feature/rag-guardrails`.
3. **Demo seed documents on the live database are `internal`, not `public`.** They existed before the migration, so the backfill used `AUTH_DEFAULT_CLASSIFICATION`. As a result, `demo_user` sees zero documents in the UI.
   - Fix if wanted: `UPDATE rag_documents SET classification='public' WHERE content_hash LIKE 'seed-%';`
   - Alternatively, upload a public document.
4. **Frontmatter metadata is stored but not used as a search pre-filter.** `doc_date`, `area`, `tags` and `summary` are now on `rag_documents` (written by `indexing/pipeline.py` `_store_frontmatter_metadata`), but `search_*_chunks` does not filter on them. A natural next feature is an `area` / `tags` filter in `ChatRequest` → `RetrievalState` → view `WHERE`.
5. **Concurrent identical uploads.** Two identical uploads racing the dedup check would hit the unique index `rag_documents_dedup_key` and return a 500 (`asyncpg.UniqueViolationError`) in `api/routes_upload.py` `upload_document`. That is unlikely with one tester; catch it and re-fetch if it matters.
6. **The UI has no admin screens.** Role and access-matrix changes are API only: `PUT /auth/access`, `PUT /auth/users/{id}/role`. Use `/docs` (Swagger) with `X-User-Id` set to the admin id.
7. **Carried over from the previous handoff and still open:**
   - the hybrid vs vector eval comparison was never run (item 2)
   - the step-7 full-text threshold bypass is loose (item 5)
   - CPU indexing is slow, about 3.5 s per chunk (item 6)
   - `rag-ai-local/template/` is missing entirely (item 7), and this doc follows the previous handoff's shape
   - stale remote branches (item 8)
8. **`CLAUDE.md` is stale.** It still says the repo is greenfield, with no commands. It should document the real layout and the commands in the Current Status table above.

## NEXT ACTION

Review and commit the work, then sort out the PR order:

```
cd D:\AI\CLAUDE\RAG
git diff --stat            # 56 entries
git add -A backend frontend .env.example rag-ai-local
git commit                 # message: add role-based authorization (roles, classifications, permission views, scoped retrieval)
# previous handoff's still-open step — base branch must reach master first:
gh pr create -R phucnh294/RAG-PR --base master --head feature/rag-guardrails
# then, after that merges:
git push -u origin feature/rbac-authorization
gh pr create -R phucnh294/RAG-PR --base master --head feature/rbac-authorization
```

Always pass `-R phucnh294/RAG-PR` to `gh` (see the previous handoff).

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE

**Decisions confirmed with the user this session:**
- **Four roles.** The user said "3 types" but listed four: user, staff, manager and admin. They confirmed the 4-level default matrix.
- **Dedup key:** (classification, hash, creator). The user rejected both the global hash dedup and having no dedup.
- **Identity:** the role dropdown picks a seeded demo user, and the frontend sends `X-User-Id`. The user rejected a raw `X-User-Role` header.
- **Delete:** creator or admin only. Managers cannot delete others' documents.

**Traps already fallen into:**
- **"Insert-if-missing" grant sync resurrects revoked grants.** A revoked grant is a missing row. A test caught this (`tests/auth/test_seed.py::test_bootstrap_keeps_grants_revoked_in_the_database`), and the fix is the `authz_seeded_grants` table. Don't "simplify" that table away.
- **The in-memory fake cannot catch SQL bugs.** `get_document_unscoped` originally read the raw table without joining `users`, so indexing logs had `created_by_username: null`. Only the live run showed it. After touching the store SQL or the views, re-run the live scenario, not just pytest.
- **The access-log line must log before resetting the contextvar,** and it reads the user from `request.state`. The user is resolved in the endpoint's task, and contextvars don't propagate back into the middleware.
- **The windowing tail fix changed behavior.** The old window chunker emitted a redundant trailing window already contained in the previous one; `_word_windows` now stops at the first window reaching the end. The existing expected windows (8 words, size 4, overlap 1) are unchanged.
- **Black and Python 3.14.** The venv runs Python 3.14.4, and plain `black` refuses with "cannot parse code formatted for Python 3.15". Always pass `--target-version py312`.
- **Bash heredocs with long Python edits failed to parse twice** ("unexpected EOF"). Writing the script to the scratchpad and running it worked. `frontend/src/App.tsx` has CRLF line endings, so string-replace scripts miss; use the Edit tool.

**Ground truth, verified live on 2026-09-25** (Docker stack; database `db-ai` on host port 5433):
- **Startup order:** schema ready → config synced (4 roles, 4 classifications, 10 grants) → admin seeded (`admin`, id `b7b90631-…`) → demo users → `Document ownership finalized (backfill: UPDATE 5)` → `Startup complete`.
- **Database state:** 10 rows in `role_classification_access`, 4 users, and 5 pre-existing documents, all `internal` and owned by admin.
- **Scenario:** manager uploaded the `confidential` Q&A doc `falcon.md`.
  - Indexing produced `{"qanda": 3}` chunks with sections `[TL;DR, Q1…, Q2…]`.
  - Staff uploading confidential got 403.
  - User and staff got 404 on list and get; manager and admin got 200.
  - Chat as user: "I don't know.", with no citation.
  - Chat as manager: a correct answer citing `falcon.md`.
  - Re-upload returned `already_exists=true` with the same id.
  - Staff and user DELETE got 404; manager DELETE got 204.
  - Manager sees 2 logs and admin sees 155.
  - The test document was deleted afterwards, so the database is back to its 5 original documents.
