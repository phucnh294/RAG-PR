---
title: Cross-Encoder Rerank Implemented — Uncommitted on feature/cross-encoder-rerank
date: 2026-09-25
type: session-handoff
area: retrieval-rerank
status: superseded
session_id: 1d4109db-3e76-42fd-818f-e1c4b5ff2169
tags: [retrieval, rerank, cross-encoder, hybrid-search, eval, docker, backend, frontend]
keywords: [feature/cross-encoder-rerank, ms-marco-MiniLM-L-6-v2, text-embeddings-inference, cpu-1.9.4, reranker-model, RERANK_CANDIDATE_K, /eval/rerank-comparison, expected_excerpt, rerank_status]
supersedes: 09252026/03_handoff-rbac-authorization.md
related: [09252026/04_cross-encoder-rerank-design.md]
next_action: Review the diff and commit on feature/cross-encoder-rerank, then open a PR. The whole stack, including reranker-model, is deployed and verified.
---

## TL;DR
- **What:** the cross-encoder reranker for step 6 is fully implemented and tested, but **not committed**.
  - Model: `cross-encoder/ms-marco-MiniLM-L6-v2`, served by a new `reranker-model` container (ONNX Runtime, TEI-compatible `/rerank`).
  - The chat UI has a per-message toggle.
  - Before/after measurement runs through `POST /eval/rerank-comparison` and the Evals page panel.
  - The golden set grew to 24 "real" queries.
- **Why:** hybrid search gets the answer into the top 5 but not reliably at #1. We needed evidence that reranking helps before paying for its latency.
- **Where:** `reranker-model/`, `docker-compose.yml`, backend `reranker_model/`, `rag_pipeline/retrieval/step4|6`, `eval/`, and frontend `ChatWindow`, `RerankComparison` and `EvalsPage`. See `04_cross-encoder-rerank-design.md`.
- **Impact:** on the live corpus, measured against the deployed container, Recall@1 went from 73.9% to 91.3%, MRR from 0.841 to 0.957 and nDCG@5 from 0.881 to 0.968. Rerank latency is 1.7 s mean and 2.3 s p95 at 10 candidates.

## Current Status
- Branch: `feature/cross-encoder-rerank`, created from `feature/rerank` at `dd7f4a6`. That base is 10 commits ahead of `master`, including RBAC and hybrid search.
- Working tree: 40 changed or new paths, **uncommitted**.
- Backend: `pytest`, 152 passed / 0 failed. `ruff`, `black --check` and `mypy src` are clean.
- Frontend: `npm run build` OK.
- Live stack: all six containers are healthy and built from this branch, including `reranker-model`, an ONNX Runtime image on `python:3.12-slim` serving on `:8080`.

## COMPLETED
- **Reranker container:**
  - `reranker-model/Dockerfile`: `python:3.12-slim` with pinned `requirements.txt`. The model is baked in at build time (`cross-encoder/ms-marco-MiniLM-L6-v2` at commit `233902d`, fp32 ONNX). The service runs as non-root on `:8080`.
  - `reranker-model/server.py`: FastAPI `POST /rerank` (TEI contract, sigmoid scores, 413 when a batch exceeds 32 texts) and `GET /health`.
  - Compose service with a Python-urllib healthcheck and `ORT_INTRA_OP_THREADS=${RERANKER_THREADS:-6}`.
  - The backend gets `RERANKER_BASE_URL=http://reranker-model:8080` and `depends_on: service_started`.
  - The default `RERANK_CANDIDATE_K` was lowered from 20 to 10 after a sweep: same quality, half the latency.
- **Backend:**
  - `RerankerClient` / `RerankerModelError`, plus a fake client and an autouse conftest fixture.
  - The step-4 pool widens to `RERANK_CANDIDATE_K` when rerank is on.
  - Step 6 is async: it scores, sorts, records `pre_rerank_rank` and falls back to the hybrid order on error.
  - `rerank_results` is written to the pipeline logs.
  - `ChatRequest.rerank`, `Citation.rerank_score` and `ChatResponsePayload.retrieval`.
- **Eval:**
  - `retrieval_ranking.py`: the shared steps 1–5 helper, and relevance by filename plus excerpt.
  - `rerank_comparison.py` and `ndcg_at_k`, `ranking_metrics` and `metrics_delta` in `scoring.py`.
  - The existing `/eval/run` recall/MRR now ignores unresolved entries, and it pins rerank off.
  - 19 new golden entries. Every excerpt was verified against the **live** indexed chunks.
- **Frontend:**
  - Rerank checkbox, saved in localStorage as `rag.rerankEnabled`.
  - Rerank status line and rerank score in citations.
  - Rerank Comparison panel on the Evals page.
- **Docs:** README (Reranking section, env table, structure), `CLAUDE.md` Commands section, `.env.example`, and design doc `04_…`.
- **Live verification:**
  - A rerank-on chat against the rebuilt backend with no reranker returned the answer with `rerank_status: failed` (fallback works).
  - The comparison ran on the live DB, first through a host ONNX stand-in and then through the deployed `reranker-model` container. The results were identical; they're in `04_…`.
  - A rerank-on chat for "Can I fly business class on a work trip?" returned `rerank_status: applied` and the correct "economy class" answer.

## NOT DONE / STILL OPEN
1. **`reranker-model` is not the official TEI image.** It is a custom ONNX Runtime image, because ghcr.io pulls are refused on this machine (see Context). To switch to TEI once pulls work, change `reranker-model/Dockerfile` and set the port in `docker-compose.yml` (`RERANKER_BASE_URL`, healthcheck) to 80.
2. **Not committed, no PR.** The user did not ask for a commit this session.
3. **Rerank latency is about 1.7 s mean on CPU.** That is acceptable next to a multi-second LLM call, but the next thing to try is a GPU or a smaller `RERANK_CANDIDATE_K`.
4. **Distractor documents are not indexed.** `03_holiday_pay_policy.md` and `07_manager_planning_distractor.md` exist only under `data/input/`. Re-upload them through the UI so the holiday query stops being skipped and the PTO distractor actually competes.
5. **Possible follow-up at `step7_combine_context.py:39`.** The threshold ignores `rerank_score`, so a reranker-promoted chunk with low cosine and no keyword match gets dropped. Only act on this if logs show it happening.
6. **Missing-reranker fallback costs about 4 s per request (DNS failure).** Consider a short `connect=` timeout at `reranker_model/client.py:45` or a circuit breaker.
7. **`CLAUDE.md` "Project status" still says "greenfield",** which is stale. The Commands section was updated but that paragraph was not.

## NEXT ACTION
Commit and open the PR:
```bash
git add -A && git commit    # on feature/cross-encoder-rerank
gh pr create --base master  # note: base is 10 commits ahead of master (RBAC + hybrid)
```
To re-verify first, run `docker compose up -d --build`, then use Evals → Rerank Comparison. Expect +17.4 pts Recall@1 at 10 candidates.

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE
- **The ghcr.io pull fails through Docker Desktop, and the problem is not the tag.**
  - `docker pull …:cpu-1.9.4` returns `error from registry: denied`, even with an empty `DOCKER_CONFIG`.
  - An anonymous `curl` to `ghcr.io/v2/huggingface/text-embeddings-inference/manifests/cpu-1.9.4` with a pull token returns **200**.
  - `docker info` shows the daemon uses proxy `http.docker.internal:3128`, so this is likely a Docker Desktop proxy or Registry Access Management setting.
  - I did not try to bypass it. Check Docker Desktop → Settings → Resources → Proxies, or sign-in and organization policy.
- **How the first numbers were obtained, before the container existed** (they were later confirmed against the deployed container):
  1. The same model's `onnx/model.onnx` and `tokenizer.json` were downloaded from huggingface.co.
  2. A TEI-compatible `/rerank` stub was served on host `:8081` (scratchpad only, not in the repo).
  3. `run_rerank_comparison` ran inside `rag-backend-1` with `settings.reranker_base_url = http://host.docker.internal:8081`.

  Sanity check: for "paid annual leave", the relevant passage scored 0.99995 and an irrelevant one 0.00005.
- **Latest TEI CPU tag on 2026-09-25 is `cpu-1.9.4`.** This came from the registry tag list, paginated with `?last=`; the first page stops at `cpu-1.2.1`, which looks like "latest" but isn't.
- **Windows trap that bit this session:** Python `Path.write_text` on this machine wrote cp1252 (an em dash became byte `0x97`, a SyntaxError) and CRLF.
  - The repo working tree is LF, with `core.autocrlf=true`.
  - `docker-compose.yml`, `index.css`, README and EvalsPage are CRLF.
  - Edit with the Edit tool, or open files with `encoding="utf-8", newline=""`.
  - `frontend/src/api/streaming.ts` and `step10_response.py` hold the NUL-byte marker (a literal NUL in the TS file). Verify it survives any edit.
- **Why the existing golden-set test changed:** `test_golden_set_catches_attacks_and_measures_retrieval_quality` never seeded documents. Recall "worked" only because unresolved entries were scored 0.0. With the new skip rule it saw `None`, so the test now uses the `seeded_corpus` fixture in `tests/eval/conftest.py`.
- **The previous handoff `03_handoff-rbac-authorization.md` said RBAC was uncommitted.** It has since been committed as `dd7f4a6`, and that handoff is superseded.
