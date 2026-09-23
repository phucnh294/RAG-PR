# RAG Pipeline

A production-oriented Retrieval-Augmented Generation (RAG) system: a React chat/upload UI, a Python (FastAPI) backend, and locally-hosted LLM/embedding models — each service running in its own Docker container.

> **Status:** early-stage. The upload + chat API and UI work end-to-end, with a real local LLM (Ollama) generating answers over an 8-step indexing pipeline and a 10-step retrieval pipeline. Documents, chunks, and embeddings persist in a real Postgres+pgvector container (`rag_documents`/`rag_chunks`/`rag_embeddings`) — similarity search runs as an actual pgvector `<=>` query, not in-memory. Embeddings are produced by a dedicated `nomic-embed-text` Ollama container, not a stub. See [Plan & documentation](#plan--documentation) for the full roadmap.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript, built with Vite, served by nginx |
| Backend API | Python, FastAPI, uvicorn |
| LLM | Ollama, running `qwen2.5:0.5b-instruct` in its own container |
| Embeddings | Ollama, running `nomic-embed-text` in its own dedicated container |
| Vector store | Postgres + pgvector (`pgvector/pgvector:pg16`) — the backend's document/chunk/embedding store |
| Orchestration | Docker Compose |

## Project structure

```
RAG/
├── docker-compose.yml          # orchestrates all containers
├── .env.example                 # copy to .env (gitignored) for Postgres credentials
├── data/input/                 # raw uploaded documents (bind-mounted volume)
├── postgres/init/               # SQL run once on first container start (enables pgvector)
├── llm-model/                  # Ollama container dedicated to chat/generation
│   ├── Dockerfile
│   └── entrypoint.sh           # starts Ollama, pulls the configured model
├── embedding-model/             # Ollama container dedicated to embeddings (nomic-embed-text)
│   ├── Dockerfile
│   └── entrypoint.sh
├── backend/                    # FastAPI application
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── pipeline-logs/           # one JSON file per indexing/retrieval run (bind-mounted, gitignored)
│   ├── src/rag_backend/
│   │   ├── main.py             # app factory, CORS, router wiring, DB pool lifecycle
│   │   ├── config.py           # pydantic-settings (env-configurable)
│   │   ├── exceptions.py       # domain error types
│   │   ├── pipeline_logging.py # writes the per-run JSON log files under pipeline-logs/
│   │   ├── api/                # routes: upload, chat, health, logs
│   │   ├── llm_model/          # client for the llm-model container
│   │   ├── embedding_model/    # client for the embedding-model container (+ fake_client.py
│   │   │                       # — the old hash-based stub, now used only by the test suite)
│   │   ├── db/                 # session.py (asyncpg pool) + postgres_store.py (real store)
│   │   ├── schemas/            # pydantic request/response models
│   │   └── storage/            # records.py (shared dataclasses) + dummy_store.py
│   │                           # (in-memory fake used only by the test suite)
│   └── tests/                  # pytest suite
├── frontend/                   # React + Vite app
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
│       ├── api/                # backend client + streaming chat reader
│       ├── components/         # ChatWindow, DocumentUpload, DocumentList, ...
│       └── pages/               # ChatPage, DocumentsPage, LogsPage
├── .claude/                    # coding standards & doc-organization rules/skills
└── rag-ai-local/                # architecture plans, design docs, Q&A knowledge base
```

## Plan & documentation

The full architecture, technical decisions, business rules, and phased build order live under [`rag-ai-local/functionality-docs/09172026/`](rag-ai-local/functionality-docs/09172026/):

- [`01_rag-pipeline-implementation-plan.md`](rag-ai-local/functionality-docs/09172026/01_rag-pipeline-implementation-plan.md) — overall architecture: pgvector schema, embedding model choice, business rules, CI/CD, phased build order.
- [`02_rag-pipeline-project-structure.md`](rag-ai-local/functionality-docs/09172026/02_rag-pipeline-project-structure.md) — the two-container LLM/embedding topology, the `data/input/` raw-file store, and the indexing/retrieval pipeline broken into individually-testable steps.

Coding conventions and where new documentation belongs are defined in [`CLAUDE.md`](CLAUDE.md) and [`.claude/rules/`](.claude/rules/).

## Running with Docker (recommended)

Brings up five containers: `postgres` (pgvector-enabled Postgres), `llm-model` (Ollama, chat), `embedding-model` (Ollama, `nomic-embed-text`), `backend` (FastAPI), `frontend` (nginx-served React build).

First, create your local env file (gitignored — never commit it):

```bash
cp .env.example .env
```

Then:

```bash
docker compose up -d --build
```

First run will download the Ollama base image and pull the chat and embedding models (a few hundred MB each), so `llm-model` and `embedding-model` may take a minute or two to report healthy. Check status with:

```bash
docker compose ps
```

Once all services show `healthy`:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (docs at http://localhost:8000/docs)
- Postgres: `localhost:5433` (credentials from `.env`) — mapped to a non-default host port because `5432` may already be taken by a native Postgres install on your machine; the container's internal port is still the standard `5432`

Stop everything with:

```bash
docker compose down
```

Uploaded documents persist on the host under `data/input/` (bind-mounted, gitignored) even after containers are removed.

### Pipeline logs

Every indexing run and every chat request writes one JSON file to `backend/pipeline-logs/{indexing,retrieval}/` (bind-mounted, gitignored) capturing the full run: for retrieval, the user's message, the normalized query, the similarity-search results, the full system prompt and messages sent to the LLM, the final answer, the citations, and per-step timings; for indexing, the filename/mime type, resulting chunk count or failure reason, and per-step timings. Browse them in the UI's **Logs** tab, or hit the API directly:

```bash
curl http://localhost:8000/logs                       # list recent runs (add ?pipeline=retrieval|indexing to filter)
curl http://localhost:8000/logs/retrieval/<log-id>     # full record for one run
```

### Configuration

Environment variables (set in `docker-compose.yml` or an `.env` file) control the backend:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` | `http://llm-model:11434` | Where the backend reaches the Ollama chat container |
| `LLM_MODEL_NAME` | `qwen2.5:0.5b-instruct` | Model pulled by `llm-model` and used for chat |
| `EMBEDDING_BASE_URL` | `http://embedding-model:11434` | Where the backend reaches the Ollama embedding container |
| `EMBEDDING_MODEL_NAME` | `nomic-embed-text` | Model pulled by `embedding-model`; also stored as `rag_embeddings.model` |
| `MAX_UPLOAD_SIZE_MB` | `25` | Upload size limit |
| `ALLOWED_MIME_TYPES` | pdf, txt, md | Accepted upload types |

`.env` (copied from `.env.example`) controls the `postgres` container's credentials — `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` — and the backend reads the same file (`env_file: .env` in `docker-compose.yml`) to connect to it, plus `POSTGRES_HOST`/`POSTGRES_PORT` (set to the internal Docker network address `postgres:5432` in compose; override for local non-Docker runs, see below).

## Running locally without Docker

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
uvicorn rag_backend.main:app --reload
```

The backend seeds 3 documents into Postgres on first startup (skipped if any document already exists). By default it expects Ollama instances at `http://llm-model:11434` and `http://embedding-model:11434` (the Docker service names) and Postgres at `localhost:5433` (the host-mapped port — see [Running with Docker](#running-with-docker-recommended)); when running outside Docker with `docker compose up -d postgres llm-model embedding-model` still providing those three containers, override the Ollama URLs:

```bash
LLM_BASE_URL=http://localhost:11434 EMBEDDING_BASE_URL=http://localhost:11435 uvicorn rag_backend.main:app --reload
```

(This assumes both models are pulled and reachable — since `llm-model` and `embedding-model` both listen on Ollama's default `11434` inside their own containers, publish them to different host ports if running both this way, or run each against a locally-installed Ollama serving both models on one port. `postgres_host`/`postgres_port` default to `localhost:5433` in `config.py` for this exact case.)

Run tests:

```bash
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on http://localhost:5173. By default it calls the backend at `http://localhost:8000`; override with a `VITE_API_BASE_URL` env var if needed.

Build for production:

```bash
npm run build
```

## Current limitations

- Documents indexed before the switch to `nomic-embed-text` (e.g. the 3 seeded documents on an existing database volume) still hold vectors from the old hash-based stub — incompatible with nomic's vector space. There is no bulk re-index tool yet; for clean local testing, drop and recreate the Postgres volume (`docker compose down -v postgres && docker compose up -d`) so everything gets re-embedded with the real model.
- `min_similarity_score` (0.7) was set from a single live sample (3 seeded documents): a true match scored ~0.91 while unrelated documents scored 0.60-0.62 for the same query — real semantic embeddings have a much higher "noise floor" than the old hash stub did. Revisit with more/varied documents; this is not a rigorously tuned value.
- The `rag_documents`/`rag_chunks`/`rag_embeddings` schema (`postgres/init/01-create-extension.sql`) was originally shaped for embedding this repo's own `rag-ai-local/*.md` knowledge base; app-uploaded documents reuse the same columns (e.g. `metadata` jsonb holds `content_hash`/`size_bytes`/`excerpts` rather than dedicated columns).
- No schema migration tool (Alembic, etc.) — the schema is applied once via the Postgres init script; changing it on a running database currently means a manual `psql` command or a volume reset.
- No authentication or rate limiting.
- The frontend's API base URL and the backend's CORS allowlist are currently hardcoded per environment (localhost/LAN) rather than templated via `.env`.

These are tracked as upcoming work in the plan documents linked above.
