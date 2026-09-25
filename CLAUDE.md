# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is **greenfield**: no application code, README, Dockerfiles, `docker-compose.yml`, or package manifests exist yet (verified — no `backend/`, `frontend/`, `src/`, `package.json`, `pyproject.toml`, or `requirements.txt`). The only real content today is the `.claude/` documentation/workflow scaffolding described below. The "Target architecture" section is forward-looking guidance for how the project is intended to be built, not a description of existing code — don't assume any of it exists until you've verified it.

## Target architecture

The intended system is a production RAG pipeline made of three independently containerized services:

- **Local LLM host** — an LLM served from its own Docker container (model/runtime to be chosen when this is scaffolded).
- **RAG backend** — Python, using **pgvector** (Postgres + the vector extension) for embedding storage and similarity search.
- **Frontend UI** — a React application.

Each service is expected to have its own Dockerfile, orchestrated by a `docker-compose.yml` at the repo root once these pieces exist. No folder layout (e.g. `backend/`, `frontend/`) has been decided yet — don't invent one; ask or follow whatever structure is introduced first.

## Documentation system (this part is real — follow it now)

Knowledge/documentation Markdown files in this repo follow a strict RAG-ready convention, defined in `.claude/rules/file-organization.md`. Key points:

- All knowledge docs live under `rag-ai-local/`, in exactly one of `QandA/` (question-and-answer files) or `functionality-docs/` (everything else: plans, design notes, investigations, post-mortems, handoffs). Nothing else may create a knowledge `.md` outside these two folders.
- Every file must start with YAML frontmatter (`title`, `date`, `type`, `area`, `status`, `tags`, etc.) plus a `TL;DR` block, so the corpus can be chunked/embedded and pre-filtered before vector search.
- Files are named with a resolved `MMDDYYYY` date prefix; `functionality-docs/` entries additionally get a two-digit sequence prefix (`NN_`) per day.
- Never start a doc from a blank file — use the templates in `rag-ai-local/template/` (`QandA_template.md`, `functionality_template.md`, `business_rule_template.md`, `session_handoff_template.md`); the schema contract lives in `rag-ai-local/template/_METADATA_SCHEMA.md`.
- Every work session should end with a handoff doc (`type: session-handoff`) before context is compacted/cleared — see Rule F in `file-organization.md`.

Python code, once it exists, must follow `.claude/rules/python-coding-standards.md` (PEP 8/black/ruff, mandatory type hints, `src/` layout, pytest, custom exceptions, `logging` not `print`, etc.).

Both rule files note they are duplicated in a `must-read.md` — if you edit a rule that's shared, update both copies.

## Skills to use instead of improvising

- **run-hello** — builds the project's Docker image, runs it as a container, and verifies the output contains "Hello". Use for Docker build/run verification (currently unusable — no Dockerfile exists yet).
- **write-qanda-doc** — writes a Q&A knowledge doc into `rag-ai-local/QandA/`.
- **write-functionality-doc** — writes a functionality/architecture/design/investigation/post-mortem doc into `rag-ai-local/functionality-docs/`.
- **write-business-rule-doc** — reverse-engineers business rules from source code into `rag-ai-local/functionality-docs/`, with CONFIRMED/INFERRED/SUSPECT trust levels and code evidence.
- **write-handoff-doc** — writes an end-of-session handoff doc so the next session can resume cold.

## Commands

Backend (from `backend/`, using its `.venv`):

- Tests: `.venv/Scripts/python -m pytest` (Windows) / `.venv/bin/python -m pytest`
- Lint / format / types: `python -m ruff check .`, `python -m black --check .`, `python -m mypy src`
- Dev server: `uvicorn rag_backend.main:app --reload`

Frontend (from `frontend/`): `npm run dev`, `npm run build` (runs `tsc -b` + `vite build`).

Full stack: `docker compose up -d --build` from the repo root (postgres, llm-model,
embedding-model, reranker-model, backend, frontend). See README.md for ports and env vars.
