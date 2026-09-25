---
title: Hybrid Search (pgvector + Postgres Full-Text) Fused with RRF
date: 2026-09-24
type: session-handoff
area: rag-retrieval
status: in-progress
session_id: 0009fab7-f0b1-4cc3-adbc-6c9b3b61b145
tags: [hybrid-search, full-text-search, rrf, pgvector, retrieval, rag-pipeline, backend, postgres]
keywords: [content_tsv, tsvector, plainto_tsquery, ts_rank_cd, reciprocal_rank_fusion, search_fulltext_chunks, ensure_fulltext_index, HYBRID_SEARCH_ENABLED, HYBRID_CANDIDATE_K, RRF_K, FULLTEXT_SEARCH_CONFIG, matched_fulltext, rag_chunks_content_tsv_idx]
supersedes: 09232026/03_handoff-guardrail-eval-harness-and-ui.md
related: [09232026/02_handoff-3-layer-guardrail-system.md]
next_action: Start Docker, run `docker compose up --build`, and confirm the backend startup log shows "Full-text index ready on rag_chunks.content_tsv" and a chat request's pipeline log has non-null text_rank values.
---

## TL;DR
- **What:** Retrieval step 4 now runs pgvector cosine search AND Postgres full-text
  search over `rag_chunks.content_tsv`, then fuses both ranked lists with Reciprocal
  Rank Fusion (`1 / (rrf_k + rank)`) and keeps the top `retrieval_top_k`.
- **Why:** Embeddings rank exact identifiers (error codes, config keys, names) badly;
  keyword search ranks them well. `content_tsv` already existed in the schema but was
  never populated or queried.
- **Where:** `postgres_store.py` (tsv on insert, new FTS query, startup backfill),
  `step4_similarity_search.py` (RRF), `step7_combine_context.py` (threshold exemption),
  `config.py`, `main.py`, the init SQL, the in-memory `dummy_store.py`, and tests.
- **Impact:** 66/66 DB-free backend tests pass (6 new), ruff clean. The real SQL has
  **never run against Postgres** — Docker was down all session.

## Current Status

**Branch:** `feature/hybrid-search`, cut from `feature/rag-guardrails` at `b42359d`
(NOT from `master` — guardrails aren't merged to master and aren't pushed; hybrid
search edits the same retrieval files). A PR to `master` will therefore also carry
the guardrail commits unless `feature/rag-guardrails` merges first.

Code change: 12 files, +313 / −10, committed together with this doc.

**Verification (exact commands, run from `backend/`):**

| Command | Result |
|---|---|
| `.\.venv\Scripts\python -m pytest -q --ignore=tests/test_routes_chat.py --ignore=tests/test_routes_logs.py --ignore=tests/test_routes_upload.py` | `66 passed, 2 warnings` |
| `.\.venv\Scripts\python -m pytest -q` (full) | `66 passed, 14 errors` — all 14 are `ConnectionRefusedError` in route tests (see NOT DONE #2); same errors on the pre-change code (verified with `git stash`) |
| `.\.venv\Scripts\python -m ruff check src tests` | `All checks passed!` |
| `.\.venv\Scripts\python -m ruff format --check src tests` | `98 files already formatted` |
| `.\.venv\Scripts\python -m mypy src` | 1 error, pre-existing (NOT DONE #3) |
| `docker compose ps` | Docker daemon not running — no live verification |

## COMPLETED

1. **Schema** — `postgres/init/01-create-extension.sql:26` adds GIN index
   `rag_chunks_content_tsv_idx` on `content_tsv`.
2. **Indexing** — `postgres_store.add_chunks` writes
   `content_tsv = to_tsvector($7::regconfig, content)` on every chunk insert.
3. **Startup migration** — `postgres_store.ensure_fulltext_index()`
   (`backend/src/rag_backend/db/postgres_store.py:254`), called from
   `main.py:19` before `seed()`: `ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT
   EXISTS`, then backfills rows where `content_tsv IS NULL`. Needed because init SQL
   only runs on a fresh volume.
4. **FTS query** — `postgres_store.search_fulltext_chunks(query_text, embedding, top_k)`
   (`postgres_store.py:218`): OR-ed `plainto_tsquery`, ordered by `ts_rank_cd`, each
   row also returns cosine similarity to the query embedding.
5. **RRF** — `step4_similarity_search.py:52` `reciprocal_rank_fusion()`; `similarity_search()`
   pulls `max(hybrid_candidate_k, top_k)` candidates from each retriever and fuses.
   `ScoredChunk` gained `rrf_score`, `vector_rank`, `text_rank`, `matched_fulltext`.
   Function name `similarity_search` kept so `pipeline.py` and `eval/runner.py`
   (recall/MRR) needed no changes — the Evals tab measures hybrid automatically.
6. **Threshold** — `step7_combine_context.py:30`: a chunk survives if cosine ≥
   `min_similarity_score` **or** full-text matched it.
7. **Logging** — step `4_similarity_search` output now has `search_mode` and per-result
   `rrf_score`/`vector_rank`/`text_rank`.
8. **Config** (`config.py:75` onward, documented in `.env.example`):
   `HYBRID_SEARCH_ENABLED=true`, `HYBRID_CANDIDATE_K=20`, `RRF_K=60`,
   `FULLTEXT_SEARCH_CONFIG=english`. Disabling hybrid restores exact old behaviour.
9. **Test double** — `dummy_store.search_fulltext_chunks` (`dummy_store.py:139`):
   regex tokens, tiny stop-word list, no stemming, ranks by count of shared terms.
   Both new store functions registered in `tests/conftest.py` `_STORE_FUNCTIONS`.
10. **Tests** — `test_step4_similarity_search.py`: keyword-only chunk wins under hybrid,
    vector-only when disabled, 2 RRF unit tests. `test_step7_combine_context.py`:
    below-threshold FTS match is kept.

## NOT DONE / STILL OPEN

1. **Real SQL never executed.** `search_fulltext_chunks` and `ensure_fulltext_index`
   are unverified against Postgres 16/pgvector. Risk spots: the
   `replace(plainto_tsquery(...)::text, '&', '|')::tsquery` rewrite, and asyncpg's
   type inference for `$3::regconfig` / `$7::regconfig` params.
2. **14 route tests need a live Postgres** (`tests/test_routes_chat.py`,
   `test_routes_logs.py`, `test_routes_upload.py`). Cause: `main.py:12` does
   `from rag_backend.db.session import close_pool, init_pool`, so conftest's
   `monkeypatch.setattr(db_session, "init_pool", ...)` doesn't reach the name bound in
   `main`. Pre-existing, not touched. Fix: in `main.py` call `db_session.init_pool()`
   via the module, or patch `rag_backend.main.init_pool` in conftest.
3. **mypy error, pre-existing:** `step7_combine_context.py:81` — `level` inferred as
   `str`, `EvidenceSummary.level` wants a `Literal`. Annotate the local as
   `Literal["high", "medium", "low"]`.
4. **No retrieval-quality comparison yet.** Eval golden set has not been run
   hybrid vs vector-only on real embeddings. The golden set also has no
   keyword-style queries (error codes/IDs), which is where hybrid should win.
5. **Handoff template missing:** `rag-ai-local/template/session_handoff_template.md`
   referenced by CLAUDE.md / Rule E does not exist in the repo; this doc copies the
   structure of the previous handoff instead.
6. **Not pushed / no PR.**

## NEXT ACTION

Start Docker Desktop, then from repo root:

```
docker compose up --build
```

Check the backend log for `Full-text index ready on rag_chunks.content_tsv (backfill:
UPDATE N)`, send one chat question, and open the newest file under
`backend/pipeline-logs/retrieval/` — step `4_similarity_search` should show
`"search_mode": "hybrid"` and at least one non-null `text_rank`. Then run the Evals
tab with `HYBRID_SEARCH_ENABLED=true` vs `false` and compare recall@k / MRR.

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE

- **OR, not AND, for the tsquery.** `plainto_tsquery`/`websearch_to_tsquery` AND every
  term; for a natural-language question that almost never matches a 200-word chunk.
  Rewriting `&`→`|` on the quoted text form is safe because the default parser never
  emits `&` inside a lexeme. Rejected: building `to_tsquery` from raw words (syntax
  errors on user punctuation).
- **Fusion in Python, not one SQL CTE.** First design was a single SQL query with a
  FULL OUTER JOIN + RRF. Rejected so RRF is a pure, unit-testable function and the
  in-memory test store only needs a simple FTS stand-in. Cost: two round-trips per
  query, negligible.
- **FTS query also returns cosine similarity** (it takes `embedding` as an argument)
  so keyword-only hits still have a real `similarity_score` for step 7 and the Layer 2
  evidence guardrail. Looks odd in a "full-text" function — it's deliberate.
- **Step 7 exemption is the key product decision** — flagged to the user as a
  trade-off; they did not object, but it hasn't been explicitly signed off. Without it, keyword-only hits (low cosine by definition) are dropped by
  the 0.7 threshold and hybrid only reorders chunks that vector search already kept.
  Downside: a chunk sharing one ordinary word with the question can reach the prompt.
  Mitigations: only top `retrieval_top_k` (5) fused results get there, and evidence
  rates such chunks `low`. If live runs show off-topic context, tighten to
  `text_rank <= N` rather than removing the exemption.
- **`content_tsv` written by the app, not a GENERATED column.** A generated column
  would hardcode `'english'`; the config is an env var. Consequence: changing
  `FULLTEXT_SEARCH_CONFIG` does NOT rebuild existing rows — set `content_tsv = NULL`
  and restart (backfill), or re-index documents.
- **Branch base trap:** `feature/rag-guardrails` is not on `origin` and not merged.
  Don't rebase `feature/hybrid-search` onto `master` without bringing guardrails along.
- **Prior handoff's "Nothing committed"** (09232026/03) is stale — its work was
  committed as `9444f75`, `4ca0fac`, `b42359d`.
