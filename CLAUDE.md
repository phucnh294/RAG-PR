# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The RAG system is built and runs as Docker services orchestrated by `docker-compose.yml`:

- **backend/** — Python FastAPI (`src/rag_backend`), pgvector for embeddings + hybrid search,
  role-based access, guardrails, reranking, semantic cache, conversations, and the **Agents
  pipeline** (`rag_backend/agents/`, see below).
- **frontend/** — React + Vite (tabs: Chat, Documents, Logs, Evals, Agents).
- **llm-model / embedding-model / vision-model** — Ollama containers (answer LLM, embeddings,
  and `qwen2.5vl:3b` for the Agents UI-analysis step).
- **reranker-model** — cross-encoder over a TEI-compatible `/rerank` API.
- **test-runner** — headless Chromium + Playwright behind `POST /capture` and `POST /run`
  (internal only). Executes the step DSL; never runs code it receives.
- **myweb** — static Register Account page at http://localhost:8080/myweb, the system under
  test for the Agents pipeline. Its rules are stated verbatim in
  `rag_backend/agents/defaults.py` — change both together.

### Agents pipeline

`rag_backend/agents/pipeline.py` runs, in order: page capture → UI analysis (vision) →
business rules → test design → business confirmation (rejected cases loop back to design) →
Playwright execution → test validation. Agents hand over through files: each agent writes
`agents/agents-result/{agent}/{input,output}/{agent}_task{id}_{datetime}.md` (readable summary,
✅/❌ result line, and a `<!-- handoff-json -->` JSON block), and the next agent's input is
parsed back from those output files (`agents/handoff.py`). The run record (`run.json`, with
every LLM attempt), README, test-case docs and per-step evidence stay in
`backend/pipeline-logs/agents/{stem}/`, shown in the Agents and Logs tabs.

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
embedding-model, reranker-model, vision-model, test-runner, myweb, backend, frontend). See
README.md for ports and env vars.

test-runner (real Chromium against myweb, also myweb's regression suite):
`docker compose run --rm test-runner python -m pytest`


# Testing Agent Workflow

For UI test-generation work, use agents in this sequence when appropriate:

1. `ui-analysis`
2. `business-analysis`
3. `test-design`
4. `test-automation`
5. `test-validation`

Do not automatically invoke all agents for every task.

Use:
- `ui-analysis` when the page structure or behavior must first be understood.
- `business-analysis` when business behavior needs to be extracted or clarified the test case.
- `test-design` when scenarios or test cases are needed.
- `test-automation` when approved test cases should become Playwright code.
- `test-validation` after execution when results or failures need diagnosis.

For simple fixes to an existing Playwright test, work directly or use only the relevant agent.

Agent outputs must be grounded in available project evidence. Do not invent requirements.

Where outputs cross agent boundaries, prefer structured Markdown or JSON-like structures rather than unstructured narrative.

The workflow is:

UI/DOM/Screenshot
    ↓
ui-analysis
    ↓
business-analysis
    ↓
test-design
    ↓
 business-analysis
    ↓
test-automation
    ↓
Playwright execution
    ↓
test-validation