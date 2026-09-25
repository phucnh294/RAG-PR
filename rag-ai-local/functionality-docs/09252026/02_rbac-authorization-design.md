---
title: Role-Based Authorization for Documents, Retrieval and Logs
date: 2026-09-25
type: functionality
area: authorization
status: implementation-complete
session_id: e4ce8334-7603-4da1-bb94-f1b2180e6010
tags: [authorization, rbac, pgvector, hybrid-search, indexing, chunking, logging, backend, frontend]
keywords: [X-User-Id, X-Request-ID, v_user_accessible_documents, v_user_accessible_chunks, role_classification_access, authz_seeded_grants, document_classifications, AUTH_ROLE_ACCESS, AUTH_DEFAULT_CLASSIFICATION, ADMIN_USERNAME, AUTH_DEV_MODE, RetrievalState, find_existing, get_document_unscoped, rag_documents_dedup_key, chunk_strategy]
files:
  - backend/src/rag_backend/auth/
  - backend/src/rag_backend/db/authz_schema.py
  - backend/src/rag_backend/db/postgres_store.py
  - backend/src/rag_backend/api/routes_auth.py
  - backend/src/rag_backend/api/routes_upload.py
  - backend/src/rag_backend/api/routes_logs.py
  - backend/src/rag_backend/rag_pipeline/indexing/frontmatter.py
  - backend/src/rag_backend/rag_pipeline/indexing/step3_chunking_strategy.py
  - backend/src/rag_backend/rag_pipeline/retrieval/state.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step4_similarity_search.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step5_metadata_filter.py
  - backend/src/rag_backend/request_context.py
  - backend/src/rag_backend/main.py
  - frontend/src/auth/identity.ts
  - frontend/src/components/RoleSelector.tsx
version: 1
last_updated: 2026-09-25
extraction_method: written-during-implementation
related_docs: [09252026/01_handoff-hybrid-search-embedding-fix-merge-gap.md]
---

## TL;DR
- **What:** Role-based authorization for the RAG system. There are 4 roles (user, staff, manager, admin) and 4 document classifications (public, internal, confidential, restricted). A role→classification access table decides who can read what.
- **Enforcement:** everywhere, through two Postgres views filtered by `user_id`:
  - document list, get and delete
  - both halves of hybrid search
  - chat citations
  - pipeline logs
- **Why:** before this change, every endpoint was open. Retrieval searched every chunk, `/logs` exposed everyone's questions, and one global hash dedup let one user's upload block everyone else's.
- **Where:**
  - **Backend:**
    - the new `auth/` package
    - `db/authz_schema.py` (tables and views)
    - `db/postgres_store.py`, where every read now requires `user_id`
    - the upload, logs and chat routes
    - indexing step3 (Q&A chunking) and retrieval steps 4, 5 and 7
  - **Frontend:** the "Acting as" role picker, plus a classification and tags selector on upload.
- **Impact:** a caller only ever sees, retrieves or gets cited documents their role may read. Verified live against real Postgres: a manager's confidential Q&A doc is answered for the manager, the user gets "I don't know", and the document returns 404 for user and staff. 135 backend tests pass.

## What the authorization system does

Every request except `/health` and `/auth/demo-users` must carry an `X-User-Id` header.

**Identity:**
- `auth.dependencies.get_current_user` loads that user from the `users` table.
- A missing or unknown id returns 401, and an inactive user returns 403.
- The user's role and allowed classifications also come from the database. The client never sends a role, so a caller cannot claim a higher one.

**What each role can do:**

| Role | Can read (default) | Can upload into | Can delete |
|---|---|---|---|
| user | public | public | own documents |
| staff | public, internal | public, internal | own documents |
| manager | + confidential | + confidential | own documents |
| admin | + restricted | everything | any readable document |

**Delete rule:** creator or admin, and only for documents the caller can currently read. A manager cannot delete a staff member's document even though they can read it.

**Status codes:**

| Case | Status |
|---|---|
| Document exists but caller can't read it | 404, same as a missing document, so its existence is never confirmed |
| Caller can read it but not delete it | 403 |
| Upload above the caller's clearance | 403 |
| Unknown classification | 422 |

## How the permission views enforce access in SQL

The access rule lives in exactly one place: the join in two views, recreated at every startup by `db/authz_schema.ensure_authorization_schema()`.

- **`v_user_accessible_documents`:**
  - joins `users` → `role_classification_access` (on role) → `rag_documents` (on classification), `WHERE u.is_active`
  - exposes `user_id` plus the document columns and `created_by_username`
- **`v_user_accessible_chunks`:** joins the documents view to `rag_chunks` and `rag_embeddings`, and exposes `user_id`, `classification`, the chunk columns, `content_tsv` and `embedding`.

**Required `user_id`:** every user-facing store function takes it as an argument and queries a view `WHERE user_id = $n`:
- `list_documents(user_id)`
- `get_document(document_id, user_id)`
- `search_similar_chunks(embedding, top_k, user_id)`
- `search_fulltext_chunks(query, embedding, top_k, user_id)`

A caller that forgets `user_id` fails to type-check. An unknown or inactive user matches zero rows, so the gate **fails closed**.

**Unscoped reads:** `get_document_unscoped`, `get_chunks` and `all_chunks` read the raw tables. They exist only for the indexing runner and seeding, and must never be called from a request handler.

## How retrieval applies permissions (RetrievalState)

**`RetrievalState`** (in `rag_pipeline/retrieval/state.py`) travels through the retrieval steps and holds:
- `request_id` and the `CurrentUser`
- `search_mode` (hybrid or vector)
- the vector and text candidate counts
- `permission_dropped_count`

**How the steps use it:**
- **Step 4:** both searches run with `user_id=state.user.id`. The permission filter is applied **inside SQL, before each LIMIT and before RRF fusion**, so a user always gets a full top-k of readable chunks.
- **Step 5:** a defence-in-depth check. It drops any chunk whose `classification` is not in the user's allowed set, or is `None`, and logs a WARNING. That warning should never fire. If it does, the SQL filter has a bug.
- **Step 7:** resolves citation filenames through the permission-scoped `get_document`.

**The retrieval log** (`pipeline-logs/retrieval/*.json`) records `user_id`, `username` and `role`, plus a `state` block with the allowed classifications and search mode, so every answer can be traced to who asked and what they could see.

## How uploads are classified and deduplicated

`POST /documents` accepts optional form fields `classification` and `tags` (comma-separated).

**Classification order** (`auth.service.resolve_upload_classification`):
1. The explicit form field.
2. The markdown frontmatter's own `classification:` line.
3. `AUTH_DEFAULT_CLASSIFICATION`.

An explicit or frontmatter choice above the caller's clearance returns 403. The default is **capped** at the user's clearance instead. The default is `internal`, but a plain `user` can only read `public`, so their uploads default to `public` rather than failing.

**Dedup key:** `(classification, content_hash, created_by)`, enforced by the unique index `rag_documents_dedup_key`.
- The same bytes, same uploader and same classification return the existing document with `already_exists=true` and skip indexing.
- A different uploader or classification creates a new document.
- This replaced the old global `find_by_hash`, where any identical file blocked everyone. That was wrong once documents have owners and visibility: user A's restricted copy would have stopped user B from indexing a public one.

## How Q&A-aware chunking works

Indexing step3 (`chunk_text`) picks a strategy from the document's structure. The choice is recorded in chunk metadata (`chunk_strategy`, `section_heading`, `question_id`) and in the indexing log.

| Strategy | When | Chunks |
|---|---|---|
| `qanda` | markdown with frontmatter `type: qanda`, or any `## Q<n>` heading | one per `##` section; `## TL;DR` is its own chunk; `###` sub-headings stay inside their question |
| `section` | other markdown with `##` headings | one per `##` section, plus the preamble as "Introduction" |
| `window` | everything else | 200-word windows with 20-word overlap (unchanged) |

**Section chunk details:**
- Every section chunk starts with `Title: <frontmatter title or filename> | Section: <heading>`, so a chunk retrieved alone still answers on its own.
- A section longer than `CHUNK_SIZE_WORDS` is sub-split into windows, and each window keeps the prefix.

**Frontmatter storage:** fields parsed by `indexing/frontmatter.py` (`date`, `area`, `tags`, TL;DR) are written to `rag_documents` (`doc_date`, `area`, `tags` merged with the upload tags, `summary`, `description`). They are ready for metadata pre-filtering, but no pre-filter uses them yet.

## How to change the access matrix and roles (configuration)

All values live in `config.py` `Settings` and can be overridden in `.env` (lists and dicts as JSON). See `.env.example`.

| Setting | Runtime effect |
|---|---|
| `AUTH_ROLES`, `AUTH_CLASSIFICATIONS` | Inserted into `roles` / `document_classifications` if missing. List order sets rank / level. |
| `AUTH_ROLE_ACCESS` | Each grant is applied **once**, tracked in `authz_seeded_grants`. A grant newly added to config is applied on the next restart. A grant an admin revoked stays revoked. |
| `AUTH_DEFAULT_CLASSIFICATION` | Classification when an upload names none, capped at the uploader's clearance. |
| `ADMIN_USERNAME` | Seeded on every startup and **forced back to role admin and active**. Restarting the backend recovers a demoted or deactivated admin. |
| `AUTH_DEV_MODE` | `true` seeds `demo_user` / `demo_staff` / `demo_manager` and enables the unauthenticated `GET /auth/demo-users` the UI picker needs. Set it to `false` once real login exists. |
| `SEED_DOCUMENTS_CLASSIFICATION` | Classification of the built-in seed docs, applied only when the database is empty. |

**Validation:** a model validator refuses to start the app if the matrix names an unknown role or classification, if the default is unknown, or if `admin` is not a role.

**Runtime changes** (admin only, and they take effect on the very next request because nothing is cached):
- `PUT /auth/access {role, classification, granted}`
- `POST /auth/users`
- `PUT /auth/users/{id}/role`
- `PUT /auth/users/{id}/active`

## Key decisions and rejected alternatives

- **Views plus a required `user_id`, not a Python post-filter.** The old step5 filtered after the top-k cut, so a user could get zero results even though readable matches existed further down. The permission filter has to run before LIMIT in SQL.
  - Rejected alternative: Postgres row-level security with `SET LOCAL app.user_id`. It would need a transaction per query on the shared asyncpg pool, and is easy to leak across pooled connections.
- **The backend loads the user from the database, and the UI never sends a role.** Rejected alternative: a raw `X-User-Role` header. Simpler, but any client could claim admin, and it would have to be torn out when real auth arrives. Swapping `X-User-Id` for a verified JWT later changes only `get_current_user`.
- **Grants are seeded once each, not insert-if-missing on every start.** The first version re-inserted missing grants on every startup, which silently resurrected any grant an admin had revoked. A revoked grant *is* a missing row. A test caught this, and `authz_seeded_grants` fixes it.
- **Schema changes run idempotently at startup** (`ensure_authorization_schema`, then `finalize_document_ownership`), not in `postgres/init/*.sql`. The init scripts only run on a fresh volume, and this follows the existing `ensure_fulltext_index` pattern.
- **Existing documents are backfilled** to `AUTH_DEFAULT_CLASSIFICATION` (internal), owned by the seeded admin. After that, `classification` is set `NOT NULL`.

## Monitoring and logs

- **Log format:** every console line carries `[req=<request-id> user=<username> role=<role>]`, via contextvars in `request_context.py` and a filter installed in `logging_config.py`.
- **Access log:** the HTTP middleware logs one line per request (method, path, status, ms, user, role). It honours an incoming `X-Request-ID` and echoes it back in the response header.
- **Audit log:** lines start with `AUTH`.
  - `AUTH denied ...` (WARNING): uploads above clearance, non-admin admin actions, delete by a non-creator.
  - `AUTH rejected ...` (WARNING): missing, unknown or inactive user.
  - `AUTH allowed ...` (INFO): role and grant changes, with actor and target.
- **Pipeline logs:** indexing logs record `created_by`, `created_by_username`, `classification`, `chunk_strategy`, and the frontmatter. Retrieval logs record the user and `RetrievalState`.
- **Who sees which logs:** `/logs` shows admins everything. Everyone else sees only their own questions (`user_id`) and their own uploads (`created_by`), and another user's log returns 404.

## Gotchas

- **Seed docs on an existing database are internal.** On a database that existed before this feature, the demo seed documents were backfilled to `internal`, so `demo_user` sees **no documents** until something `public` is uploaded. Only a fresh database gets `SEED_DOCUMENTS_CLASSIFICATION=public` seed docs.
- **The DELETE status code depends on read access, not only ownership.** A user deleting a document they can't read gets 404, not 403. That is deliberate (no existence leak), but it surprises people testing with the wrong role.
- **Demoting a creator can lock them out of their own document.** After a demotion, the creator can no longer read, and therefore no longer delete, their own higher-classified documents. `can_delete` requires read access first. An admin must clean up.
- **Admins cannot change their own role or deactivate themselves.** This is a lock-out guard, and the API returns 403.
- **The access-log line's context comes from `request.state.user`, not contextvars.** The user is resolved inside the endpoint's task, and contextvars do not flow back into the middleware.
- **The fake store must mirror the views.** Tests run against the in-memory `storage/dummy_store.py`, which mirrors the views' rule (`_readable_classifications`). SQL-only bugs are invisible to pytest. The raw-table `get_document_unscoped` missing `created_by_username` was only caught by the live check. Always run the live check below after changing the views or store SQL.
- **Retrieval tests need registered documents.** Chunks added under a document id that has no document row are invisible in both the real views and the fake. The retrieval test helper `register_document` (in `tests/rag_pipeline/retrieval/conftest.py`) exists for this.

## Verification

**Unit and route tests.** From `backend/`:

```
.venv\Scripts\python -m pytest -q        # expect: 135 passed
.venv\Scripts\ruff check src tests       # All checks passed!
.venv\Scripts\mypy src                   # Success: no issues found
```

**Live check against the Docker stack:**

```
docker compose build backend frontend
docker compose up -d --no-deps --force-recreate backend frontend
```

The startup log must show these steps in order:
1. `Authorization schema ready`
2. `Authorization config synced`
3. `Admin user seeded from env`
4. `Demo users seeded`
5. `Document ownership finalized`
6. `Startup complete`

**Database checks** on port 5433:

```
SELECT role, classification FROM role_classification_access ORDER BY 1, 2;  -- 10 rows, the matrix above
SELECT classification, count(*), count(created_by) FROM rag_documents GROUP BY 1;  -- no NULL owners
```

**Scenario to run** (this was run on 2026-09-25 and all expectations held):
- **Upload:** manager uploads a `confidential` Q&A markdown.
  - The indexing log shows `chunk_strategy: qanda`, `{"qanda": 3}` and sections `[TL;DR, Q1…, Q2…]`.
- **Clearance:**
  - Staff uploading `confidential` gets 403.
  - User and staff get 404 on `GET /documents/{id}`, and the document is absent from their lists. Manager and admin see it.
- **Chat:**
  - As user, the answer is "I don't know." with no citation.
  - As manager, the answer is correct and cites the document.
- **Dedup and delete:**
  - The same re-upload by the manager returns `already_exists=true` with the same id.
  - Staff and user DELETE get 404. Manager (the creator) DELETE gets 204.
- **Logs:** every log line has `req=… user=… role=…`, and `X-Request-ID` is echoed.
