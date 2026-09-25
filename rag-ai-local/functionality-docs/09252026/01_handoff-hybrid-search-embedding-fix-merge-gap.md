---
title: Hybrid Search + Embedding Batch Fix Merged — Not Yet in Master
date: 2026-09-25
type: session-handoff
area: rag-retrieval
status: superseded
session_id: 0009fab7-f0b1-4cc3-adbc-6c9b3b61b145
tags: [hybrid-search, full-text-search, rrf, embedding, indexing, timeout, pull-request, git, backend, docker]
keywords: [feature/rag-guardrails, a96b610, PR #10, PR #11, PR #12, EmbeddingModelError, EMBEDDING_BATCH_SIZE, EMBEDDING_REQUEST_TIMEOUT_SECONDS, httpx.ReadTimeout, content_tsv, ensure_fulltext_index, matched_fulltext, --force-recreate]
supersedes: 09242026/01_handoff-hybrid-search-rrf.md
related: [09232026/03_handoff-guardrail-eval-harness-and-ui.md]
next_action: Open a PR from feature/rag-guardrails to master so hybrid search (#11) and the embedding fix (#12) actually reach master — they were merged into feature/rag-guardrails, not master.
---

## TL;DR
- **What:** Hybrid search (pgvector + Postgres full-text, fused with RRF) was verified
  live, an indexing bug (embedding timeout leaving documents stuck in `pending`) was
  found and fixed, and all work was shipped as stacked PRs #10, #11, #12 — all merged.
- **Why:** Hybrid search improves keyword/identifier recall; the indexing bug made any
  upload over ~20 chunks silently produce zero chunks.
- **Where:** `feature/rag-guardrails` @ `a96b610` holds everything; `master` @ `23c5d97`
  has only the guardrails (#10).
- **Impact:** 84/84 backend tests pass on `feature/rag-guardrails`. **#11 and #12 are
  NOT in `master`** — a follow-up PR is required (see NEXT ACTION).

## Current Status

**The merge gap (most important fact in this doc):**

| PR | head → base | State | In `master`? |
|---|---|---|---|
| #10 guardrails + eval harness | `feature/rag-guardrails` → `master` | MERGED (`23c5d97`) | yes |
| #11 hybrid search | `feature/hybrid-search` → `feature/rag-guardrails` | MERGED (`3774c30`) | **no** |
| #12 embedding batch fix | `fix/embedding-batch-timeout` → `feature/rag-guardrails` | MERGED (`a96b610`) | **no** |

#10 merged into `master` first; #11/#12 were then merged into their stacked base
`feature/rag-guardrails` (GitHub hadn't retargeted them to `master`). Verified with
`git merge-base --is-ancestor 0e3d45b origin/master` → exit 1 (same for `ab2bcd9`) and
`git log origin/master..origin/feature/rag-guardrails` → 5 commits.

**Local repo:** on `feature/rag-guardrails`, fast-forwarded to `origin/feature/rag-guardrails`
(`a96b610`). Remote branches `feature/hybrid-search` and `fix/embedding-batch-timeout`
still exist on origin (fully merged, safe to delete).

**Running Docker stack:** all 5 containers up. `rag-backend-1` was built from the
hybrid + fix code (same code as `a96b610`), so the running app matches the merged branch.

**Verification (run from `backend/` on `a96b610`, Postgres container up):**

| Command | Result |
|---|---|
| `.\.venv\Scripts\python -m pytest -q` | `84 passed, 2 warnings` |
| `.\.venv\Scripts\python -m ruff check src tests` | `All checks passed!` |
| `.\.venv\Scripts\python -m mypy src` | 1 error — pre-existing, `step7_combine_context.py` (NOT DONE #3) |

Note: the 14 route tests (`tests/test_routes_*.py`) only pass while the Postgres
container is running — see NOT DONE #4.

## COMPLETED

1. **Hybrid search verified live** (code described in the superseded
   `09242026/01_handoff-hybrid-search-rrf.md`, still accurate):
   - Backend startup log: `Full-text index ready on rag_chunks.content_tsv (backfill: UPDATE 24)`.
   - `POST /chat` "How many vacation days do employees get?" → HTTP 200, correct answer
     ("20 days of paid annual leave"); pipeline log step `4_similarity_search` showed
     `"search_mode": "hybrid"` and non-null `vector_rank`/`text_rank` on all 5 results.
   - After re-upload, 21/21 chunks had `content_tsv` populated (checked via psql).
2. **Indexing bug diagnosed and fixed** (PR #12, commit `ab2bcd9`):
   - Symptom: slow upload, then document in `rag_documents` with 0 rows in `rag_chunks`,
     `status = pending` forever.
   - Cause: `embedding_model/client.py` sent all chunks in one `/api/embed` request with
     a 30s timeout; `httpx.ReadTimeout` escaped `run_indexing`'s `except RagBackendError`.
   - Fix: batches of `EMBEDDING_BATCH_SIZE=8`; timeout default 60s (per batch); httpx
     errors wrapped in new `EmbeddingModelError(RagBackendError)` in `exceptions.py`, so
     the document is marked `failed` with a message naming the batch.
   - 4 new tests: `backend/tests/embedding_model/test_client.py` (3, using
     `httpx.MockTransport` via the new `transport=` ctor arg) and one in
     `backend/tests/rag_pipeline/indexing/test_pipeline.py`.
   - Live check: re-uploaded `vb-company-policy-rag-test.md` (3,638 words) → `ready`
     in 76s, 21 chunks. That document remains in the DB (id `42a33eca-…`).
3. **Stacked PRs** #10/#11/#12 created with descriptions and merged by the user.

## NOT DONE / STILL OPEN

1. **Hybrid search + embedding fix are not in `master`.** Needs PR
   `feature/rag-guardrails` → `master` (NEXT ACTION).
2. **Hybrid vs vector-only eval comparison never run.** Evals tab with
   `HYBRID_SEARCH_ENABLED=true` vs `false`; compare recall@k/MRR. Golden set
   (`backend/src/rag_backend/eval/golden_set.json`) has no keyword/identifier-style
   queries — add some, that's where hybrid should win.
3. **mypy error, pre-existing:** `backend/src/rag_backend/rag_pipeline/retrieval/step7_combine_context.py`
   in `_assess_evidence` — `level` inferred as `str`, `EvidenceSummary.level` wants
   `Literal["high","medium","low","none"]`. Annotate the local variable.
4. **Route tests hit a real Postgres.** `backend/src/rag_backend/main.py:12` imports
   `init_pool` by name, so `tests/conftest.py`'s `monkeypatch.setattr(db_session,
   "init_pool", ...)` doesn't affect it; without the container, 14 route tests error
   with `ConnectionRefusedError`. Fix: call `db_session.init_pool()` via the module in
   `main.py`, or patch `rag_backend.main.init_pool` in conftest.
5. **Step-7 full-text threshold bypass is loose** (`step7_combine_context.py`,
   `or item.matched_fulltext`): live, 11+ chunks full-text-matched a normal question on
   common words, so all 5 fused chunks bypassed the 0.7 cosine threshold (two at 0.63 /
   0.68). Answer was still correct. Tighten to `text_rank <= 3` if off-topic context
   appears.
6. **Indexing is slow, by nature of CPU embedding:** ~3.5s/chunk end-to-end in the
   live test. Fix made it reliable, not fast. Options if it matters: GPU, a smaller
   embedding model, or larger chunks.
7. **Missing template:** `rag-ai-local/template/session_handoff_template.md` (referenced
   by CLAUDE.md / Rule E) doesn't exist; this doc follows the previous handoff's shape.
8. **Stale remote branches** `feature/hybrid-search`, `fix/embedding-batch-timeout` —
   merged, can be deleted.

## NEXT ACTION

Open the PR that carries #11 and #12 into `master`:

```
gh pr create -R phucnh294/RAG-PR --base master --head feature/rag-guardrails \
  --title "Merge hybrid search and embedding batch fix into master"
```

`git log --oneline origin/master..origin/feature/rag-guardrails` should list exactly
5 commits (`86d6b33`, `0e3d45b`, `ab2bcd9`, `3774c30`, `a96b610`) plus this handoff
doc's commit if it was committed on that branch.

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE

- **Stacked-PR trap (hit this session):** with base PR #10 targeting `master` and #11/#12
  targeting `feature/rag-guardrails`, merging #10 first and then #11/#12 lands #11/#12
  on `feature/rag-guardrails` only. GitHub's auto-retarget happens only if the base
  branch is *deleted* on merge. Next time: after merging the base PR, retarget the
  stacked PRs to `master` (`gh pr edit N --base master`) *before* merging them, or
  enable "automatically delete head branches".
- **`gh pr list` returned `[]`** even with PRs present; `-R phucnh294/RAG-PR` fixed it.
  Always pass `-R` in this repo.
- **`docker compose up -d --build backend` hung** after the image built — the old
  container was never replaced (checked with `docker inspect rag-backend-1 --format
  "{{.Image}}"`). Reliable sequence: `docker compose build backend` then
  `docker compose up -d --no-deps --force-recreate backend`.
- **Measured embedding latency** (nomic-embed-text on CPU, from inside the backend
  container, ~200-word inputs): 1 → 6.9s, 5 → 16.5s, 21 → 32.9s. Basis for batch 8 /
  timeout 60s. Timeout is per batch, not per document.
- **Re-uploading a stuck document does nothing:** `/documents` dedupes by SHA-256 and
  returns the existing `pending` record with `already_exists: true` without
  re-indexing. Delete it first, then upload.
- **Why the fix branch was based on `feature/rag-guardrails`, not `master`:**
  `exceptions.py`/`config.py` had guardrail-era changes, so the fix wouldn't apply
  cleanly to `master`; and basing it off hybrid would have coupled two unrelated PRs.
- **The user merges PRs themselves** — they merged #10–#12 without further instruction
  between sessions; don't assume a PR is still open, check with `gh pr list -R … --state all`.
