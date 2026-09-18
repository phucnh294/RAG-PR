---
title: RAG Pipeline Project Structure and Indexing/Retrieval Process
date: 2026-09-17
type: functionality
area: rag-pipeline
status: investigation
tags: [rag, pgvector, ollama, fastapi, indexing, retrieval, project-structure, docker]
keywords: [llm-model, embedding-model, data/input, run_indexing, run_retrieval, content_hash, MIN_SIMILARITY_SCORE, vector_cosine_ops]
related: [09172026/01_rag-pipeline-implementation-plan.md]
---

## TL;DR
- **What:** A refined project structure that visibly separates the LLM (chat) model, the embedding model, the API layer, raw-document storage, and the RAG pipeline itself — with the pipeline split into two explicit processes, indexing and retrieval, each broken into single-responsibility steps.
- **Why:** Doc 01 defined the overall architecture but bundled chat and embeddings into one Ollama container and didn't specify where raw uploaded files live on disk. This doc gives each concern its own folder/container and makes the indexing/retrieval flow step-addressable, so each step can be built, tested, and reasoned about independently.
- **Where:** Future `llm-model/`, `embedding-model/`, `data/input/`, and `backend/src/rag_backend/rag_pipeline/{indexing,retrieval}/` (none exist yet — this doc specifies what they should look like).
- **Impact:** Supersedes doc 01's single-Ollama-container topology with two dedicated containers; adds a durable `data/input/` raw-file store; adds business rule 11 (raw file retention); everything else in doc 01 (pgvector schema, business rules 1–10, CI/CD, frontend, phased build order) still applies unchanged.

## Relationship to doc 01

This document is an addendum to [01_rag-pipeline-implementation-plan.md](01_rag-pipeline-implementation-plan.md), not a replacement. Only the container topology for the LLM and embedding models changes (one shared Ollama container → two dedicated ones); the Postgres/pgvector schema, the ten business rules, the CI/CD setup, the frontend requirements, and the phased build order from doc 01 are all still in effect and are referenced here rather than repeated.

## Revised project structure

```
RAG/
├── docker-compose.yml
├── .env.example / .env (gitignored)
├── data/
│   └── input/                          # raw uploaded documents, durable volume, NOT in git
│       └── <document_id>/<original_filename>
├── llm-model/                          # dedicated Ollama container — chat/generation only
│   ├── Dockerfile                      # FROM ollama/ollama:latest
│   └── entrypoint.sh                   # ollama serve; pull ${LLM_MODEL_NAME}
├── embedding-model/                    # dedicated Ollama container — embeddings only
│   ├── Dockerfile
│   └── entrypoint.sh                   # ollama serve; pull ${EMBEDDING_MODEL_NAME}
├── backend/
│   ├── Dockerfile, pyproject.toml, alembic.ini
│   ├── src/rag_backend/
│   │   ├── main.py, config.py, logging_config.py, exceptions.py
│   │   ├── api/                        # API for UI upload and chat
│   │   │   ├── deps.py
│   │   │   ├── routes_upload.py        # POST /documents, GET /documents, DELETE /documents/{id}
│   │   │   ├── routes_chat.py          # POST /chat (streaming)
│   │   │   └── routes_health.py
│   │   ├── auth/api_key.py
│   │   ├── middleware/ (rate_limit.py, request_logging.py)
│   │   ├── db/ (session.py, models.py, migrations/)
│   │   ├── storage/
│   │   │   └── input_store.py          # save/read/delete raw files under data/input/<doc_id>/
│   │   ├── llm_model/                  # client for the llm-model container
│   │   │   ├── client.py               # chat(messages), stream_chat(messages)
│   │   │   └── config.py               # LLM_BASE_URL, LLM_MODEL_NAME
│   │   ├── embedding_model/            # client for the embedding-model container
│   │   │   ├── client.py               # embed_texts(texts) -> list[list[float]]
│   │   │   └── config.py               # EMBEDDING_BASE_URL, EMBEDDING_MODEL_NAME
│   │   ├── rag_pipeline/
│   │   │   ├── indexing/               # INDEXING PROCESS
│   │   │   │   ├── step1_receive_and_store.py
│   │   │   │   ├── step2_extract_text.py
│   │   │   │   ├── step3_chunk_text.py
│   │   │   │   ├── step4_embed_chunks.py
│   │   │   │   ├── step5_persist_chunks.py
│   │   │   │   ├── step6_finalize_status.py
│   │   │   │   └── pipeline.py         # run_indexing(document_id) orchestrates steps 1-6
│   │   │   └── retrieval/              # RETRIEVAL PROCESS
│   │   │       ├── step1_embed_query.py
│   │   │       ├── step2_similarity_search.py
│   │   │       ├── step3_apply_threshold.py
│   │   │       ├── step4_build_prompt.py
│   │   │       ├── step5_generate_answer.py
│   │   │       └── pipeline.py         # run_retrieval(query, ...) orchestrates steps 1-5
│   │   └── schemas/ (documents.py, chat.py)
│   └── tests/
├── frontend/                           # React UI: chat + document upload
└── rag-ai-local/
```

Each `stepN_*.py` file is a single-responsibility module (one function, type-hinted, per `.claude/rules/python-coding-standards.md`). `pipeline.py` in each subpackage is the only place that sequences the steps, so the pipeline's shape is readable in one file while each step stays independently testable and swappable without touching its neighbors.

## Indexing process — step definitions

The indexing process turns an uploaded file into searchable, embedded chunks in Postgres.

1. **step1_receive_and_store** — accepts uploaded bytes from `routes_upload.py`; computes the sha256 `content_hash` (dedup key); if that hash already exists, short-circuits and returns the existing document (doc 01 business rule 3) instead of processing again; otherwise writes the raw file to `data/input/<document_id>/<filename>` via `storage/input_store.py` and inserts a `documents` row with `status=pending`.
2. **step2_extract_text** — reads the stored raw file back and extracts plain text according to `mime_type` (PDF via pypdf/pdfplumber, txt/md via direct decode); raises a typed extraction error on failure rather than swallowing it, so the pipeline can mark the document `failed` with a real error message.
3. **step3_chunk_text** — splits the extracted text into fixed-size chunks with overlap (`CHUNK_SIZE_TOKENS`/`CHUNK_OVERLAP_TOKENS` from doc 01's config), preserving page number / character offset metadata so later citations can point at the right spot in the source document.
4. **step4_embed_chunks** — batches the chunk texts and calls `embedding_model/client.py::embed_texts()` against the dedicated embedding-model container to get one 768-dim vector per chunk.
5. **step5_persist_chunks** — bulk-inserts the chunks plus their embeddings into the `chunks` table (the `vector(768)` column defined in doc 01); if any part of the batch fails, all chunks for this document are rolled back rather than leaving a partially-indexed document (doc 01 business rule 10).
6. **step6_finalize_status** — sets `documents.status=ready` (or `failed` with `error_message` populated) and closes out the matching `ingestion_jobs` row.

`indexing/pipeline.py::run_indexing(document_id)` runs steps 2–6 as a background task immediately after step 1 has already returned the upload response — the caller gets a document id/job id back right away instead of waiting for extraction and embedding to finish.

## Retrieval process — step definitions

The retrieval process turns a user's chat message into a grounded, cited answer.

1. **step1_embed_query** — takes the user's message from `routes_chat.py` and calls `embedding_model/client.py::embed_texts()` to get its embedding, using the same embedding model and dimension as indexing (this consistency is mandatory — see Gotchas).
2. **step2_similarity_search** — runs the pgvector cosine-distance (`<=>`) query against `chunks`, returning up to `RETRIEVAL_TOP_K` scored chunks, with optional metadata filters (e.g. restrict to specific document ids).
3. **step3_apply_threshold** — if no returned chunk clears `MIN_SIMILARITY_SCORE`, the pipeline short-circuits into the "I don't know based on the available documents" response (doc 01 business rule 5) instead of continuing to prompt construction.
4. **step4_build_prompt** — assembles the system prompt, the surviving chunks' content, and their chunk/document ids (for citations) into the message list that will be sent to the LLM.
5. **step5_generate_answer** — calls `llm_model/client.py::stream_chat()` against the dedicated llm-model container, streaming tokens back through `routes_chat.py` to the UI, and attaches the citation list (built from step 2's surviving chunks, per doc 01 business rule 8) to the final response payload.

`retrieval/pipeline.py::run_retrieval(query, filters)` runs steps 1–5 synchronously per request — unlike indexing, this is not backgrounded, because the user is actively waiting on the streamed answer.

## Docker/compose changes from doc 01

- The single `ollama` service from doc 01 is replaced by two services: `llm-model` (built from `llm-model/`, volume `llm_models:/root/.ollama`, `mem_limit: 8g`, healthcheck against `/api/tags`) and `embedding-model` (built from `embedding-model/`, volume `embedding_models:/root/.ollama`, `mem_limit: 2g` — `nomic-embed-text` is much smaller than the chat model — healthcheck against `/api/tags`).
- The `backend` service now declares `depends_on: postgres (healthy), llm-model (healthy), embedding-model (healthy)` instead of depending on a single `ollama` service.
- A new bind mount, `./data/input` on the host mapped into the backend container (e.g. at `/app/data/input`), holds raw uploaded files so they survive container restarts and live on the host filesystem rather than being baked into any image.
- Config env vars split from doc 01's single `OLLAMA_BASE_URL`/`OLLAMA_CHAT_MODEL`/`OLLAMA_EMBED_MODEL` into four: `LLM_BASE_URL`, `LLM_MODEL_NAME`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL_NAME`.

## New business rule (in addition to doc 01's ten)

11. **Raw file retention** — the raw uploaded file under `data/input/<document_id>/` is retained for exactly as long as its `documents` row exists. `DELETE /documents/{id}` must delete both the database rows (cascade, per doc 01 rule 9) **and** the corresponding raw file/folder under `data/input/`. A raw file with no matching `documents` row, or a `documents` row with no raw file on disk, is a bug — the two stores must never diverge.

## Gotchas

- **Double Ollama overhead:** running two Ollama containers instead of one (as doc 01 originally specified) roughly doubles total Ollama memory and startup time. This was an intentional tradeoff for independent scaling and runtime isolation between the chat and embedding workloads — revisit if resource constraints become a problem.
- **Input folder / database sync:** every code path that creates or deletes a `documents` row must also create or delete the matching raw file (business rule 11). If a future change adds a new way to remove a document (e.g. a bulk-delete endpoint), it must go through the same `storage/input_store.py` deletion path, not just delete the database row.
- **Embedding consistency between indexing and retrieval:** both `rag_pipeline/indexing/step4_embed_chunks.py` and `rag_pipeline/retrieval/step1_embed_query.py` call the same `embedding_model/client.py`. If the embedding model or its config ever changes, both call sites are affected simultaneously — there is no way to embed chunks with one model and queries with another; the vector space would no longer be comparable.
- **Step files own logic, not order:** `pipeline.py` is the only file allowed to know the step sequence. Reordering the pipeline (e.g. moving the threshold check before or after prompt building) should only ever require editing `pipeline.py`, never the step modules themselves.

## Verification

- Confirm the two-container split works: `docker compose up llm-model embedding-model` and `curl` each one's `/api/tags` — both should list their respective pulled model only (chat model absent from embedding-model's list and vice versa).
- Confirm `data/input/` sync: upload a document, verify a file appears under `data/input/<document_id>/`; delete the document via the API, verify the file/folder is gone.
- Confirm indexing step isolation: unit test each `stepN_*.py` in `rag_pipeline/indexing/` independently (e.g. `step3_chunk_text` given a fixed string produces the expected chunk boundaries) without needing a live database or Ollama container.
- Confirm retrieval step isolation: unit test `step3_apply_threshold` returns the "I don't know" signal when given an empty/low-score chunk list, without needing a live LLM call.
