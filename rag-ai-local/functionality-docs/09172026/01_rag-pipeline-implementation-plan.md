---
title: RAG Pipeline Production Implementation Plan
date: 2026-09-17
type: functionality
area: rag-pipeline
status: investigation
tags: [rag, pgvector, ollama, fastapi, react, docker, architecture, planning]
keywords: [nomic-embed-text, qwen2.5:7b-instruct, hnsw, ivfflat, vector_cosine_ops, X-API-Key, MIN_SIMILARITY_SCORE, RETRIEVAL_TOP_K]
related: [09172026/02_rag-pipeline-project-structure.md]
---

> **Superseded detail:** the single shared Ollama container described in "Docker / orchestration plan" and "Repository layout" below has been superseded by [02_rag-pipeline-project-structure.md](02_rag-pipeline-project-structure.md), which splits it into two dedicated containers (`llm-model/`, `embedding-model/`) and adds a `data/input/` raw-file store. Everything else in this document (pgvector schema, business rules 1–10, CI/CD, frontend requirements, phased build order) is still current.

## TL;DR
- **What:** Full architecture and build plan for a production RAG pipeline: an Ollama-hosted local LLM (chat + embeddings), a FastAPI + pgvector backend, and a React frontend, each in its own Docker container.
- **Why:** The repo is greenfield — no code exists yet. This doc fixes the technical decisions (embedding model, schema, module boundaries, business rules) before any implementation starts, so build work has a single source of truth instead of ad hoc choices.
- **Where:** Future `backend/`, `frontend/`, `llm/`, and root `docker-compose.yml` (none exist yet — this doc specifies what they should look like).
- **Impact:** Defines the target repo layout, the embedding/LLM model choices, the Postgres/pgvector schema, the required backend modules, ten enforced business rules, and a five-phase build order with verification steps for each phase.

## What this is

A pre-implementation design document for a RAG pipeline with four containers: a local LLM host (Ollama), a Python/FastAPI backend using pgvector for retrieval, a Postgres+pgvector database, and a React frontend. No code exists yet in this repo — this document is the blueprint the phased build order (below) works from.

## Repository layout

```
RAG/
├── docker-compose.yml, docker-compose.override.yml.example
├── .env.example / .env (gitignored), .gitignore, README.md, Makefile
├── .github/workflows/{backend-ci.yml,frontend-ci.yml}
├── backend/
│   ├── Dockerfile, pyproject.toml, alembic.ini
│   ├── src/rag_backend/
│   │   ├── main.py, config.py, logging_config.py, exceptions.py
│   │   ├── api/ (deps.py, routes_ingest.py, routes_query.py, routes_health.py)
│   │   ├── auth/api_key.py
│   │   ├── middleware/ (rate_limit.py, request_logging.py)
│   │   ├── db/ (session.py, models.py, migrations/)
│   │   ├── ingestion/ (extractors.py, chunking.py, hashing.py, pipeline.py)
│   │   ├── retrieval/ (embeddings.py, search.py)
│   │   ├── generation/ (prompting.py, ollama_client.py)
│   │   └── schemas/ (documents.py, query.py)
│   └── tests/
├── frontend/
│   ├── Dockerfile, nginx.conf, package.json
│   └── src/ (api/client.ts, api/streaming.ts, components/{ChatWindow,MessageBubble,CitationList,DocumentUpload,DocumentList}.tsx, pages/{ChatPage,DocumentsPage}.tsx, state/authStore.ts)
├── llm/ (Dockerfile, entrypoint.sh)
└── rag-ai-local/ (existing doc corpus, untouched)
```

`backend/` uses `src/rag_backend/` per the src-layout rule in `.claude/rules/python-coding-standards.md`. `llm/` (not a generic `docker/` folder) wraps the Ollama service specifically. `docker-compose.yml` stays at the repo root as the single orchestration source of truth for all four containers (postgres, ollama, backend, frontend).

## Embedding and LLM model decision

- **Embedding model:** `nomic-embed-text` served by Ollama, 768-dim vectors, via Ollama's OpenAI-compatible `/api/embeddings` endpoint.
- **Chat model default:** `qwen2.5:7b-instruct` (~4.7GB at Q4 quantization) — good instruction-following at a size that runs on modest local hardware. Swappable via the `OLLAMA_CHAT_MODEL` env var; `llama3.1:8b-instruct` is documented as an alternative in `.env.example`.
- **pgvector contract:** the `chunks.embedding` column is declared `vector(768)` at table-creation time. This dimension is a hard contract — switching to a differently-dimensioned embedding model later requires a migration that drops/recreates the column and re-embeds every existing chunk. There is no in-place way to change vector dimension.
- **Why Ollama-only, not sentence-transformers in-process:** running embeddings through Ollama (rather than loading a sentence-transformers model directly in the backend process) avoids bundling torch/CUDA into the backend Docker image, keeping it smaller and avoiding GPU-driver coupling. It also means one runtime (Ollama) to version and monitor instead of two independent ML runtimes. `nomic-embed-text` is competitive with `all-MiniLM`/`BGE-small` on retrieval benchmarks, so there's no meaningful quality cliff from this choice. The accepted tradeoff is that every embed call becomes an HTTP round trip to the Ollama container instead of an in-process call — mitigated by batching embedding requests and running ingestion as a background task so it never blocks the upload response.

## Postgres / pgvector schema

Base image: `pgvector/pgvector:pg16`. The first Alembic migration must run `CREATE EXTENSION IF NOT EXISTS vector;` before creating any table that uses the `vector` type.

**documents**
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| filename | text not null | original upload name |
| content_hash | text not null unique | sha256 of raw file bytes — dedup key |
| mime_type | text not null | |
| size_bytes | bigint not null | |
| status | text not null default 'pending' | pending / processing / ready / failed |
| error_message | text null | populated on failed |
| version | int not null default 1 | incremented on explicit re-ingest of the same logical doc |
| uploaded_by | text null | API key id |
| created_at / updated_at | timestamptz | |

**chunks**
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| document_id | uuid FK → documents, on delete cascade | |
| chunk_index | int not null | ordering within document |
| content | text not null | raw chunk text |
| token_count | int not null | |
| page_number | int null | PDFs only |
| char_offset_start / char_offset_end | int null | txt/md only |
| embedding | vector(768) not null | |
| created_at | timestamptz | |
| unique (document_id, chunk_index) | | |

**ingestion_jobs**
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| document_id | uuid FK → documents, on delete cascade | |
| status | text not null default 'queued' | queued / running / succeeded / failed |
| started_at / finished_at | timestamptz null | |
| error_message | text null | |
| created_at | timestamptz | |

**Indexing:** `CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);`. HNSW was chosen over IVFFlat because it gives better recall/speed at query time without needing a pre-tuned `lists` parameter sized to table row count, and it degrades more gracefully as the table grows — IVFFlat centroids need periodic retraining after large inserts, HNSW does not. The accepted tradeoff is slower index build/insert time and higher memory use, which is acceptable because ingestion is not the latency-critical path (queries are). Supporting indexes: `documents(content_hash)` (already implied by the unique constraint), `chunks(document_id)`, `ingestion_jobs(document_id, status)`.

## Required backend modules

- **Config** (`config.py`, pydantic-settings): `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `DATABASE_URL`, `CHUNK_SIZE_TOKENS` (default 500), `CHUNK_OVERLAP_TOKENS` (default 50), `RETRIEVAL_TOP_K` (default 5), `MIN_SIMILARITY_SCORE` (default 0.5), `API_KEYS`, `RATE_LIMIT_PER_MINUTE` (default 60), `MAX_UPLOAD_SIZE_MB` (default 25), `ALLOWED_MIME_TYPES`, `LOG_LEVEL`.
- **Ingestion** (`ingestion/`): `extractors.py` — `extract_text(file_bytes, mime_type) -> str` (pypdf/pdfplumber for PDF, direct decode for txt/md); `chunking.py` — `chunk_text(text, chunk_size, overlap) -> list[Chunk]` (fixed-size token-based with overlap); `hashing.py` — `hash_bytes(data: bytes) -> str` (sha256 hex digest); `pipeline.py` — `run_ingestion(document_id)` background task orchestrating extract → chunk → batch-embed → bulk insert → status update.
- **Retrieval** (`retrieval/`): `embeddings.py` — `embed_texts(texts: list[str]) -> list[list[float]]` (batched Ollama calls); `search.py` — `similarity_search(query_embedding, top_k, min_score, filters) -> list[ScoredChunk]` using the pgvector cosine distance operator `<=>`, with optional metadata filters.
- **Generation** (`generation/`): `prompting.py` — `build_prompt(query, chunks) -> Messages`, a system prompt instructing the model to answer only from the provided context, cite chunk ids, and say "I don't know" when context is insufficient; `ollama_client.py` — `stream_chat(messages) -> AsyncIterator[str]` calling Ollama's `/api/chat` with `stream: true`.
- **API layer** (`api/`): `routes_ingest.py` (POST/GET/DELETE `/documents`, GET `/documents/{id}/status`); `routes_query.py` (POST `/query`, streaming response with a citations payload); `routes_health.py` (`/health` liveness, `/health/ready` checking DB + Ollama reachability).
- **Auth** (`auth/api_key.py`): a FastAPI dependency reading the `X-API-Key` header, validated against an env-based key list for v1 — noted upgrade path to a DB-backed `api_keys` table with per-key rate limits/expiry.
- **Middleware** (`middleware/`): `rate_limit.py` (slowapi, keyed by API key/IP); `request_logging.py` (attaches a request id, logs method/path/status/latency as structured JSON).
- **Persistence** (`db/`): SQLAlchemy 2.0 async models, `pgvector.sqlalchemy.Vector(768)` type for the embedding column, Alembic migrations under `db/migrations/versions/`.

## Business rules (must be enforced in code, not aspirational)

1. **Max upload size** — reject uploads over `MAX_UPLOAD_SIZE_MB` (default 25MB) with HTTP 413, checked before reading the full request body into memory.
2. **Allowed file types** — only `application/pdf`, `text/plain`, `text/markdown` accepted; anything else returns HTTP 415, enforced against `ALLOWED_MIME_TYPES`.
3. **Deduplication** — `documents.content_hash` (sha256 of raw bytes) is unique; uploading identical bytes returns the existing document record (`already_exists: true`) instead of creating a duplicate row or duplicate chunks.
4. **Re-ingestion of changed content** — a different `content_hash` for what the caller considers "the same" document creates a *new* document row by default (additive versioning); the old document's chunks are not auto-deleted. Silent overwrite happens only if the caller explicitly passes a `replaces_document_id` or deletes the old document first. This prevents accidental data loss on re-upload.
5. **Minimum similarity threshold** — if no retrieved chunk's cosine similarity is at or above `MIN_SIMILARITY_SCORE` (default 0.5), the system must respond "I don't know based on the available documents" rather than calling the LLM with weak or irrelevant context.
6. **Max chunks per query** — never inject more than `RETRIEVAL_TOP_K` chunks (default 5) into the prompt context, with a hard ceiling (e.g. 20) enforced in config validation regardless of what a caller requests.
7. **Rate limits** — each API key is limited to `RATE_LIMIT_PER_MINUTE` (default 60) requests/minute; exceeding it returns HTTP 429.
8. **Citation requirement** — every generated answer must include the chunk id(s)/document id(s) it was grounded on, derived deterministically from the retrieval set actually sent to the model (not parsed out of the model's free-text output). An answer with zero citations, outside the explicit "I don't know" case, is a bug.
9. **Retention/deletion** — `DELETE /documents/{id}` is a hard, irreversible cascade delete (removes chunks and ingestion_jobs via FK). There is no soft-delete/undo in v1; a future `deleted_at` column is a noted extension point, not built now.
10. **Ingestion failure handling** — if extraction or embedding fails partway through a document, `documents.status` must be set to `failed` with `error_message` populated, and any partially-inserted chunks for that document must be rolled back. A document must never be left in `ready` status with only partial chunks.

## Frontend requirements

- **ChatPage** (`ChatWindow.tsx`, `MessageBubble.tsx`, `CitationList.tsx`) — text input, streamed assistant response rendered incrementally via fetch + `ReadableStream` (or `EventSource` if the backend exposes SSE); each assistant message ends with a collapsible citations panel listing source document name, chunk excerpt, and similarity score.
- **DocumentsPage** (`DocumentUpload.tsx`, `DocumentList.tsx`) — drag-and-drop/file-picker upload with a progress indicator; a document list with status badges (pending/processing/ready/failed) polled via `GET /documents`; delete with a confirmation step given rule 9's irreversibility.
- **Auth** — v1 has no full login UI: a simple API-key field stored in `authStore.ts` (localStorage), sent as `X-API-Key` on every request via `api/client.ts`. JWT/user accounts are a noted future extension, not built now.
- **Backend communication** — REST for upload/list/delete/health; streaming fetch (or SSE) for `/query`. `api/client.ts` centralizes the base URL (`VITE_API_BASE_URL` env var) and auth header injection; `api/streaming.ts` handles the query endpoint's streamed response.

## Docker / orchestration plan

- **`llm/Dockerfile`** — `FROM ollama/ollama:latest`, with an `entrypoint.sh` that runs `ollama serve`, waits for readiness, then pulls `${OLLAMA_EMBED_MODEL}` and `${OLLAMA_CHAT_MODEL}`. Volume `ollama_models:/root/.ollama` persists the model cache across container restarts so models aren't re-pulled every time.
- **`backend/Dockerfile`** — multi-stage build; final stage `python:3.12-slim` running as a non-root `appuser`; `HEALTHCHECK` hitting `GET /health`.
- **`frontend/Dockerfile`** — multi-stage build: `node:20-alpine` builds the app, `nginx:alpine` (non-root) serves the static output.
- **`docker-compose.yml`** (root) wires four services: `postgres` (`pgvector/pgvector:pg16`, `pg_isready` healthcheck, `mem_limit: 1g`), `ollama` (built from `llm/`, internal-only port 11434, `/api/tags` healthcheck, `mem_limit: 8g` sized for a 7–8B Q4 model), `backend` (`depends_on` postgres and ollama with `service_healthy` conditions, `/health` healthcheck, `mem_limit: 1g`), `frontend` (`depends_on` backend, published as `3000:8080`). All services use `restart: unless-stopped`. Secrets (`POSTGRES_PASSWORD`, `API_KEYS`) are supplied via a gitignored `.env` referenced with `env_file:` — never hardcoded in the compose file or any Dockerfile. `.env.example` is committed with placeholder values and comments. Named volumes: `pgdata`, `ollama_models`.

## CI/CD

- `.github/workflows/backend-ci.yml` — on PR: checkout, set up Python 3.12, install deps, run `ruff check .`, `black --check .`, `mypy src/`, `pytest --cov`.
- `.github/workflows/frontend-ci.yml` — on PR: checkout, set up Node 20, `npm ci`, `npm run lint` (eslint), `npm run build`, `npm test`.
- Optional non-blocking follow-up: a Docker build validation job for all three Dockerfiles, to catch broken images early without a full compose integration test in CI.

## Phased build order

1. **Core loop validation (no API yet)** — `docker-compose.yml` with only `postgres` + `ollama`; an Alembic migration creating `documents`/`chunks`/`ingestion_jobs` plus the HNSW index; a standalone `backend/scripts/smoke_ingest.py` that ingests one sample text file, chunks it, embeds via Ollama, inserts into pgvector, then runs a hardcoded query and prints the top-k results. This validates that Ollama is reachable, the embedding dimension matches the column, and pgvector returns sane cosine distances — before any API code exists.
2. **FastAPI backend** — build out `api/`, `ingestion/`, `retrieval/`, `generation/`, `auth/`, `middleware/`; wire `routes_ingest.py`, `routes_query.py`, `routes_health.py` into `main.py`; add the backend Dockerfile and compose service; write unit tests for chunking, hashing, prompting, search.
3. **React frontend** — scaffold a Vite+React+TS app with `ChatPage`, `DocumentsPage`, and the streaming client; add the frontend Dockerfile and compose service; manually test end-to-end via browser against the Phase 2 backend.
4. **Hardening** — enforce auth middleware on all routes, wire in rate limiting, add structured logging with request ids, switch Docker containers to non-root users, finalize healthchecks/restart policies/resource limits, complete `.env.example`.
5. **CI/CD** — add the GitHub Actions workflows for backend and frontend lint+test on PR; optionally add the Docker build validation job.

## Verification

- **Phase 1** — run `smoke_ingest.py`; assert the embedding vector length is 768; assert the top-1 retrieved chunk is the expected sample sentence; run `psql -c "\d chunks"` and confirm the `embedding` column is `vector(768)` and the HNSW index exists.
- **Phase 2** — run `pytest` for unit tests covering chunking boundary/overlap correctness, hashing-based dedup, and prompting (citations always included, "I don't know" path triggers when no chunk clears `MIN_SIMILARITY_SCORE`); run integration tests against a test Postgres (testcontainers or a compose test profile) with mocked Ollama HTTP calls hitting `routes_ingest`/`routes_query`.
- **Phase 3** — `docker-compose up`, upload a sample PDF through the UI, ask a question that references its content, and confirm the streamed answer renders with a correct citation list pointing at the right source document.
- **Phase 4** — `curl /health` and `/health/ready` return 200; a request without `X-API-Key` returns 401; exceeding the rate limit returns 429; `docker exec <container> whoami` confirms containers run as a non-root user.
- **Phase 5** — open a PR containing an intentional lint violation and confirm CI fails; fix it and confirm CI passes.

## Gotchas / decisions to remember

- The `vector(768)` dimension is fixed to `nomic-embed-text`. Swapping embedding models later is not a config change — it requires a schema migration and a full re-embed of every existing chunk.
- HNSW indexes are chosen deliberately over IVFFlat despite slower inserts, because IVFFlat's `lists` parameter needs to be sized to table row count up front and its centroids degrade without periodic retraining as data grows — a maintenance burden this design avoids.
- Re-ingesting a document with different content does **not** silently replace the old version (rule 4) — this is intentional to avoid data loss, but means callers must explicitly request replacement or the old chunks will keep answering queries alongside the new ones.
- Document deletion is a hard cascade delete with no undo (rule 9) — there is no soft-delete safety net in v1.
