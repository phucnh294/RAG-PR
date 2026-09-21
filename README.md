# RAG Pipeline

A production-oriented Retrieval-Augmented Generation (RAG) system: a React chat/upload UI, a Python (FastAPI) backend, and locally-hosted LLM/embedding models — each service running in its own Docker container.

> **Status:** early-stage. The upload + chat API and UI work end-to-end, with a real local LLM (Ollama) generating answers over an 8-step indexing pipeline and a 10-step retrieval pipeline. Storage is still the in-memory dummy store, and embeddings are a deterministic stub — a Postgres+pgvector container now runs alongside the app but the backend isn't wired to it yet. See [Plan & documentation](#plan--documentation) for the full roadmap.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript, built with Vite, served by nginx |
| Backend API | Python, FastAPI, uvicorn |
| LLM | Ollama, running `qwen2.5:0.5b-instruct` in its own container |
| Embeddings | Deterministic stub (bag-of-words hashing) — a dedicated Ollama `nomic-embed-text` container is planned |
| Vector store | Postgres + pgvector container running (`pgvector/pgvector:pg16`) — not yet wired to the backend |
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
├── backend/                    # FastAPI application
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/rag_backend/
│   │   ├── main.py             # app factory, CORS, router wiring
│   │   ├── config.py           # pydantic-settings (env-configurable)
│   │   ├── exceptions.py       # domain error types
│   │   ├── api/                # routes: upload, chat, health
│   │   ├── llm_model/          # client for the llm-model container
│   │   ├── schemas/            # pydantic request/response models
│   │   └── storage/            # in-memory dummy document store (seeded)
│   └── tests/                  # pytest suite
├── frontend/                   # React + Vite app
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
│       ├── api/                # backend client + streaming chat reader
│       ├── components/         # ChatWindow, DocumentUpload, DocumentList, ...
│       └── pages/               # ChatPage, DocumentsPage
├── .claude/                    # coding standards & doc-organization rules/skills
└── rag-ai-local/                # architecture plans, design docs, Q&A knowledge base
```

## Plan & documentation

The full architecture, technical decisions, business rules, and phased build order live under [`rag-ai-local/functionality-docs/09172026/`](rag-ai-local/functionality-docs/09172026/):

- [`01_rag-pipeline-implementation-plan.md`](rag-ai-local/functionality-docs/09172026/01_rag-pipeline-implementation-plan.md) — overall architecture: pgvector schema, embedding model choice, business rules, CI/CD, phased build order.
- [`02_rag-pipeline-project-structure.md`](rag-ai-local/functionality-docs/09172026/02_rag-pipeline-project-structure.md) — the two-container LLM/embedding topology, the `data/input/` raw-file store, and the indexing/retrieval pipeline broken into individually-testable steps.

Coding conventions and where new documentation belongs are defined in [`CLAUDE.md`](CLAUDE.md) and [`.claude/rules/`](.claude/rules/).

## Running with Docker (recommended)

Brings up four containers: `postgres` (pgvector-enabled Postgres), `llm-model` (Ollama), `backend` (FastAPI), `frontend` (nginx-served React build).

First, create your local env file (gitignored — never commit it):

```bash
cp .env.example .env
```

Then:

```bash
docker compose up -d --build
```

First run will download the Ollama base image and pull the chat model (a few hundred MB), so `llm-model` may take a minute or two to report healthy. Check status with:

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

### Configuration

Environment variables (set in `docker-compose.yml` or an `.env` file) control the backend:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` | `http://llm-model:11434` | Where the backend reaches the Ollama chat container |
| `LLM_MODEL_NAME` | `qwen2.5:0.5b-instruct` | Model pulled by `llm-model` and used for chat |
| `MAX_UPLOAD_SIZE_MB` | `25` | Upload size limit |
| `ALLOWED_MIME_TYPES` | pdf, txt, md | Accepted upload types |

`.env` (copied from `.env.example`) controls the `postgres` container's credentials — `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`. These aren't consumed by the backend yet (see [Current limitations](#current-limitations)).

## Running locally without Docker

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
uvicorn rag_backend.main:app --reload
```

The backend seeds 3 dummy documents in memory on startup. By default it expects an Ollama instance at `http://llm-model:11434` (the Docker service name) — when running outside Docker, override it:

```bash
LLM_BASE_URL=http://localhost:11434 uvicorn rag_backend.main:app --reload
```

(This assumes an Ollama instance is running locally on port 11434 with the configured model pulled.)

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

- Documents and chunks live in an in-memory dummy store (resets on restart); the `postgres`/pgvector container now runs but the backend doesn't persist to it yet.
- Embeddings are a deterministic bag-of-words hashing stub, not a real model — similarity search reflects word overlap, not semantic meaning.
- No authentication or rate limiting.
- The frontend's API base URL and the backend's CORS allowlist are currently hardcoded per environment (localhost/LAN) rather than templated via `.env`.

These are tracked as upcoming work in the plan documents linked above.
