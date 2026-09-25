---
title: Cross-Encoder Reranking (Step 6) with UI Toggle and Before/After Measurement
date: 2026-09-25
type: functionality
area: retrieval-rerank
status: implementation-complete
session_id: 1d4109db-3e76-42fd-818f-e1c4b5ff2169
tags: [retrieval, rerank, cross-encoder, hybrid-search, eval, docker, backend, frontend]
keywords: [ms-marco-MiniLM-L-6-v2, ms-marco-MiniLM-L6-v2, onnxruntime, ORT_INTRA_OP_THREADS, RERANKER_THREADS, text-embeddings-inference, TEI, /rerank, RerankerClient, RerankerModelError, rerank_status, pre_rerank_rank, rerank_score, RERANK_CANDIDATE_K, RERANK_ENABLED_DEFAULT, RERANKER_BASE_URL, /eval/rerank-comparison, run_rerank_comparison, expected_excerpt, nDCG, MRR, Recall@1]
files:
  - reranker-model/Dockerfile
  - reranker-model/server.py
  - docker-compose.yml
  - backend/src/rag_backend/reranker_model/client.py
  - backend/src/rag_backend/reranker_model/fake_client.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step4_similarity_search.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step6_reranking.py
  - backend/src/rag_backend/rag_pipeline/retrieval/pipeline.py
  - backend/src/rag_backend/rag_pipeline/retrieval/state.py
  - backend/src/rag_backend/eval/rerank_comparison.py
  - backend/src/rag_backend/eval/retrieval_ranking.py
  - backend/src/rag_backend/eval/scoring.py
  - backend/src/rag_backend/eval/golden_set.json
  - frontend/src/components/ChatWindow.tsx
  - frontend/src/components/RerankComparison.tsx
version: 2
last_updated: 2026-09-25
extraction_method: written-during-implementation
related_docs: [09242026/01_handoff-hybrid-search-rrf.md, 09252026/02_rbac-authorization-design.md]
---

## TL;DR
- **What:** Step 6 of retrieval now reorders the hybrid-search candidates with a cross-encoder, `cross-encoder/ms-marco-MiniLM-L-6-v2`. The model is served by its own `reranker-model` container: `python:3.12-slim` plus ONNX Runtime, with the model baked in at a pinned revision, exposing a TEI-compatible `POST /rerank` on `:8080`. The chat UI has a per-message checkbox that turns reranking on or off. `POST /eval/rerank-comparison` measures ranking quality with and without reranking on the same candidate pool.
- **Why:** hybrid search (RRF) finds the right chunk but often doesn't rank it first. We needed a number that shows whether a reranker on top of hybrid search is worth its latency.
- **Where:**
  - the new `reranker-model/` container
  - backend `reranker_model/` client and `step6_reranking.py`
  - the step-4 candidate widening
  - the `eval/rerank_comparison.py` runner
  - the frontend `ChatWindow` toggle and the `RerankComparison` panel on the Evals page
- **Impact:** measured on the live corpus with 23 golden queries, k=5:

  | Metric | Before | After |
  |---|---|---|
  | Recall@1 | 73.9% | **91.3%** |
  | MRR | 0.841 | **0.957** |
  | nDCG@5 | 0.881 | **0.968** |
  | Recall@5 | 100% | 100% (unchanged) |

  5 queries improved, 1 worsened and 17 were unchanged. A reranker outage falls back to the hybrid order, so it never fails a chat request.

## What cross-encoder reranking does in the retrieval pipeline
The RAG retrieval pipeline runs these steps in order:
1. embed the question
2. hybrid search (pgvector cosine plus Postgres full-text, fused with RRF)
3. permission filter
4. **rerank**
5. similarity threshold
6. prompt
7. LLM

The rerank step changes only the ORDER of the chunks and which of them survive the final `retrieval_top_k` cut.

A cross-encoder reads the question and one passage together and outputs a single relevance score. A bi-encoder such as nomic-embed-text embeds each side separately and compares vectors. The cross-encoder is far more accurate at judging whether this passage answers this question. It is also too slow to run over the whole corpus, which is why it only rescores the few dozen candidates that hybrid search already found.

## How a rerank-enabled request flows
1. **Opt-in.** `POST /chat` takes `{"message": ..., "rerank": true|false}`. When `rerank` is missing, `RERANK_ENABLED_DEFAULT` (false) applies. The UI always sends its checkbox value.
2. **Step 4 widens the pool.** When `RetrievalState.rerank_enabled` is set, `similarity_search` returns `max(retrieval_top_k, RERANK_CANDIDATE_K)` fused candidates (10 by default) instead of 5. Without this, the reranker could only shuffle the 5 chunks hybrid search had already chosen, and could never promote the right chunk from, say, position 8.
3. **Step 6 scores and sorts.** `step6_reranking.rerank()`:
   1. sends every `(question, chunk.content)` pair to `POST /rerank` on the reranker container, in batches of `RERANKER_BATCH_SIZE`
   2. records each chunk's `pre_rerank_rank`
   3. sorts by `rerank_score` (a sigmoid probability in [0, 1])
   4. cuts to `retrieval_top_k`

   Python's sort is stable, so equal scores keep their hybrid order.
4. **Status travels to the UI.** `RetrievalState.rerank_status` is one of `disabled`, `applied`, `failed` or `skipped`. It is sent back with the rerank duration in the trailing payload's new `retrieval` field. Citations carry `rerank_score`. The chat bubble shows either "Reranked by cross-encoder in N ms" or "Rerank failed — showing hybrid search order".
5. **Logs show the rank shift.** Every retrieval log (Logs tab) gets `rerank_results`, which records for each surviving chunk its `pre_rerank_rank`, `rerank_score`, cosine and RRF score. Live traffic can be inspected the same way as the offline eval.

## How the rerank before/after measurement works
`POST /eval/rerank-comparison` (admin only) calls `eval/rerank_comparison.py::run_rerank_comparison`. For each "real" golden-set entry it:
1. Runs steps 1–5 once to build a candidate pool of `RERANK_CANDIDATE_K` chunks, using `eval/retrieval_ranking.py::retrieve_candidates`, the same steps chat runs.
2. Scores two arms on that **same pool**:
   - **baseline** = the hybrid order `[:k]`
   - **reranked** = step 6 `[:k]`

   Because the pool is shared, any difference comes from the reranker alone.
3. Finds the relevant chunk's rank in each arm with `find_relevant_rank`. A chunk is relevant when:
   - its document's **filename** matches, so a re-uploaded duplicate still counts, and
   - when the entry has an `expected_excerpt`, the chunk contains that excerpt (ignoring case and whitespace).

   The excerpt makes the metric chunk-level. For a 21-chunk policy document, ranking *some* chunk of it first is not the same as ranking the chunk that holds the answer first.

The report contains:
- Recall@1, Recall@k, MRR and nDCG@k for each arm, plus the differences
- improved, worsened and unchanged counts
- `pool_recall`: the share of queries whose target was in the pool at all, which is the ceiling any reranker can reach
- mean and p95 rerank latency
- `skipped_queries`: entries whose expected document isn't indexed or visible to the admin, listed instead of scored as misses

The run is retrieval-only: no guardrails, threshold or LLM calls.

The golden set grew from 5 to 24 "real" entries. The new ones cover three kinds of query:
- paraphrased questions, e.g. "Can I fly business class on a work trip?" whose answer is "economy class"
- keyword-heavy questions (Orbit Portal, Aegis Console, $1,275,000)
- questions with near-duplicate distractors, e.g. "annual PTO allowance", which the manager-planning distractor document repeats word for word without answering it

## Measured result on the live corpus (2026-09-25)
Setup:
- live Postgres corpus of 8 documents / 36 chunks, admin user
- hybrid search, k=5, 20 candidates
- 23 queries scored; 1 skipped because `03_holiday_pay_policy.md` is not indexed

| Metric | Hybrid | Hybrid + rerank | Δ |
|---|---|---|---|
| Recall@1 | 73.9% | 91.3% | +17.4 pts |
| Recall@5 | 100% | 100% | ±0 |
| MRR | 0.841 | 0.957 | +0.116 |
| nDCG@5 | 0.881 | 0.968 | +0.087 |

What the numbers say:
- Hybrid search already gets the answer into the top 5 every time (`pool_recall` 100%). Its weakness is order.
- The cross-encoder moved the answer to #1 in 5 queries:
  - "annual PTO allowance" 4→1
  - "business class" 4→1
  - "security training" 3→1
  - "lost laptop" 2→1
  - "paid annual leave" 2→1
- It pushed one from #1 to #2: "How many days a week can I work from home?"
- Top-1 precision matters here because the small `qwen2.5:0.5b` answer model leans heavily on citation [1].

The first numbers came from a temporary host-side stand-in. They were re-measured with the deployed `reranker-model` container and matched exactly.

Latency against the deployed container (fp32 on CPU, 6 ONNX threads) depends on how many candidates are reranked (`RERANK_CANDIDATE_K`):

| Candidates | Recall@1 / MRR / nDCG after rerank | Mean latency | p95 latency |
|---|---|---|---|
| 10 | 0.913 / 0.957 / 0.968 | 1.7–1.8 s | 2.3–2.4 s |
| 15 | same | 2.6 s | 3.4 s |
| 20 | same | 3.5 s | 5.1 s |

Quality was identical at every pool size, because every win came from hybrid ranks 2–4. That is why the default is 10.

## Key decisions and rejected alternatives
- **ONNX Runtime image built on Docker Hub, instead of the official TEI image.**
  - The first plan was TEI (`ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4`).
  - On the dev machine Docker Desktop's proxy returns `denied` for every ghcr.io pull, even though anonymous HTTP access to the same manifest returns 200.
  - `reranker-model/server.py` (FastAPI, about 100 lines) keeps TEI's exact `/rerank` contract, so switching back to TEI later means changing only the Dockerfile and the port.
  - This avoids torch and sentence-transformers, which would add 1–2 GB.
  - Ollama cannot serve cross-encoders at all.
- **The model is baked into the image at a pinned revision** (`233902d`, fp32 `onnx/model.onnx`), not downloaded into a volume at startup. The container starts ready, and every build serves identical weights.
- **fp32, not the int8 `model_quint8_avx2.onnx`.** Measured: int8 took 2.23 s and fp32 2.42 s for 20 pairs, with the same ranking. A 8% speedup doesn't justify the quantization risk.
- **MiniLM-L-6 instead of L-12.** L-6 is about twice as fast on CPU with nearly the same MS MARCO quality. The measured gains show it is enough for this corpus.
- **Per-request toggle, default off.** The user asked for a UI switch. Default-off keeps existing API callers' behavior and latency unchanged.
- **The step-7 cosine threshold stays unchanged when reranking.** The rerank score decides the order, not whether a chunk is relevant enough. Keeping one threshold also keeps chat behavior comparable with rerank on and off. The rejected alternative was to let chunks survive on `rerank_score` alone; see Gotchas.
- **Measure on a shared candidate pool, not on two separate chat runs.** Two runs would mix retrieval noise into the difference. A shared pool isolates the reranker.
- **Chunk-level relevance (`expected_excerpt`) for long documents.** Document-level relevance would call the policy doc a hit whenever any of its 21 chunks ranked first, and that hides exactly what reranking is supposed to fix.
- **Unresolved golden entries are skipped, not scored as misses.** This applies to both the new comparison and the existing `/eval/run` recall and MRR, which now ignore "real" entries whose document isn't indexed. Scoring them as misses would measure the corpus, not retrieval.

## Configuration settings for reranking
| Setting | Default | Runtime effect |
|---|---|---|
| `RERANK_ENABLED_DEFAULT` | `false` | Applies only when a `/chat` body omits `rerank`. |
| `RERANK_CANDIDATE_K` | `10` | Pool size step 4 returns when reranking is on. Bigger means more chances to promote the answer, but latency grows linearly with it (about 1.7 s at 10, 3.5 s at 20). |
| `RERANKER_BASE_URL` | `http://reranker-model:8080` | Set by docker-compose for the backend. |
| `RERANKER_MODEL_NAME` | `cross-encoder/ms-marco-MiniLM-L6-v2` | Only the label shown in the report. The served model is fixed by the `MODEL_REPO`/`MODEL_REVISION` build args. |
| `RERANKER_THREADS` | `6` | Compose passes it as `ORT_INTRA_OP_THREADS`. Measured with 12 logical CPUs: 1 thread 7.0 s, 4 threads 3.0 s, 6 threads 2.2 s, 12 threads 3.7 s (hyperthreads contend). Set it to about the physical core count. |
| `RERANKER_REQUEST_TIMEOUT_SECONDS` | `15` | Per `/rerank` request. When it expires, the request falls back to the hybrid order. |
| `RERANKER_BATCH_SIZE` | `32` | Must stay ≤ TEI's `--max-client-batch-size` (32 by default), or TEI rejects the request. |

The image is about 90 MB of model plus the Python dependencies, all pinned in `reranker-model/requirements.txt`. The backend waits for `service_started`, not `service_healthy`, so a broken reranker never blocks chat.

## Gotchas
- **A chunk the reranker promotes can still be dropped by the step-7 threshold.** The threshold checks cosine ≥ 0.7 or a full-text match. The reranker can move a low-cosine chunk with no keyword match into the top 5, and step 7 then removes it. The reranker's choice is silently undone for that chunk. If live logs show this often, add a rerank-score survival rule.
- **When the reranker container is missing, each rerank-enabled request pays the DNS failure time.** About 4 s was observed before falling back. The answer still arrives, with status `failed`. Start `reranker-model` or untick the box.
- **`/rerank` returns results sorted by score, not by input position** (in TEI and in `server.py` alike). `RerankerClient` maps them back by `index`. Forgetting this would attach scores to the wrong chunks.
- **Rerank scores look tiny for long chunks, and that's normal.** Sigmoid scores such as 0.0003 for the best of five 200-word chunks still rank correctly. Only the order matters, which is one more reason step 7 keeps its cosine threshold rather than using a rerank-score cutoff.
- **The model repo was renamed to `cross-encoder/ms-marco-MiniLM-L6-v2`** (no hyphen between L and 6). The old name redirects. The Dockerfile uses the new name with a pinned commit.
- **ghcr.io pulls can fail behind Docker Desktop's proxy** (`error from registry: denied`), even though anonymous HTTP access to the same manifest returns 200. This is a local Docker Desktop registry-access or proxy setting, not a bad tag.
- **Distractor docs must be indexed for the hardest cases to count.** `03_holiday_pay_policy.md` and `07_manager_planning_distractor.md` exist under `data/input/` but are not indexed in the live database. The holiday query is skipped, and the distractor doesn't compete, until they are re-uploaded.

## Verification
- **Backend unit and integration tests** (152 pass): from `backend/`, run `.venv/Scripts/python -m pytest`. Key files:
  - `tests/rag_pipeline/retrieval/test_step6_reranking.py`: disabled passthrough, reorder with prior rank, fallback on `RerankerModelError`
  - `tests/reranker_model/test_client.py`
  - `tests/eval/test_rerank_comparison.py`: an inverting reranker produces the expected negative deltas; skipped entries; admin-only endpoint
- **Lint:** `ruff check .`, `black --check .` and `mypy src` are all clean.
- **Frontend:** from `frontend/`, `npm run build` passes.
- **Live stack:**
  1. Run `docker compose up -d --build`.
  2. Wait until `docker compose ps` shows `reranker-model` as healthy (about 20 s, since no download is needed).
  3. In the chat, tick **Rerank results with cross-encoder** and ask "Can I fly business class on a work trip?". The bubble should read "Reranked by cross-encoder in N ms", and citations should show `rerank …` scores.
  4. On **Evals → Rerank Comparison**, click Run. Expect positive Recall@1, MRR and nDCG deltas similar to the table above.
