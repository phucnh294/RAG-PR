---
title: Guardrail Evaluation Harness + UI
date: 2026-09-23
type: session-handoff
area: rag-guardrails
status: implementation-complete
session_id: 0c008d26-2ebb-4b3c-b062-c5b25fc33568
tags: [guardrails, eval, golden-set, recall, mrr, refusal-rate, block-rate, rag-pipeline, backend, frontend]
supersedes: 09232026/02_handoff-3-layer-guardrail-system.md
related: [09232026/01_handoff-step-logging-nomic-embeddings-prompt-unification.md]
---

## TL;DR
- **What:** Added a golden-set evaluation harness (`backend/src/rag_backend/eval/`) and
  a UI page for the 3-layer guardrail system from the prior session: 3 query
  categories — real (recall/MRR), expect (refusal_rate), attack (block_rate) — plus
  false_block_rate tracked on real/expect, a `POST /eval/run` endpoint, and a
  pytest test asserting `false_block_rate == 0.0`.
- **Why:** The guardrail system had no way to measure whether it actually works — no
  golden query set, no retrieval-quality metric, no visibility outside raw JSON logs.
- **Where:** New `backend/src/rag_backend/eval/` package, `api/routes_eval.py`, new
  `frontend/src/pages/EvalsPage.tsx` (4th "Evals" tab), `backend/tests/eval/`.
- **Impact:** 74/74 backend tests pass (2 new), ruff/black clean, frontend `tsc
  --noEmit` clean, `POST /eval/run` smoke-tested end-to-end via `TestClient` with the
  same fakes as the test suite (see Current Status). Nothing committed yet.

## Current Status

**Branch:** `feature/rag-guardrails` (unchanged from the prior handoff — still nothing
committed; this session's work adds to the same uncommitted working tree). This doc
**supersedes** `02_handoff-3-layer-guardrail-system.md` as the "what's the current
state" reference — that doc's description of the 3 guardrail layers themselves is
still accurate and doesn't need to be re-read, but for "what's done overall" read this
one.

```
 M .env.example
 M backend/src/rag_backend/config.py
 M backend/src/rag_backend/exceptions.py
 M backend/src/rag_backend/llm_model/client.py
 M backend/src/rag_backend/main.py
 M backend/src/rag_backend/rag_pipeline/retrieval/pipeline.py
 M backend/src/rag_backend/rag_pipeline/retrieval/step10_response.py
 M backend/src/rag_backend/rag_pipeline/retrieval/step7_combine_context.py
 M backend/src/rag_backend/schemas/chat.py
 M backend/tests/conftest.py
 M backend/tests/rag_pipeline/retrieval/test_pipeline.py
 M backend/tests/rag_pipeline/retrieval/test_step10_response.py
 M backend/tests/rag_pipeline/retrieval/test_step7_combine_context.py
 M backend/tests/rag_pipeline/retrieval/test_step8_build_prompt.py
 M backend/tests/test_routes_chat.py
 M frontend/src/App.tsx
 M frontend/src/api/client.ts
 M frontend/src/api/streaming.ts
 M frontend/src/components/ChatWindow.tsx
 M frontend/src/components/MessageBubble.tsx
 M frontend/src/index.css
?? backend/src/rag_backend/api/routes_eval.py
?? backend/src/rag_backend/eval/
?? backend/src/rag_backend/guardrails/
?? backend/src/rag_backend/rag_pipeline/retrieval/step2b_input_guardrail.py
?? backend/src/rag_backend/rag_pipeline/retrieval/step9b_output_guardrail.py
?? backend/tests/eval/
?? backend/tests/guardrails/
?? backend/tests/rag_pipeline/retrieval/test_step2b_input_guardrail.py
?? backend/tests/rag_pipeline/retrieval/test_step9b_output_guardrail.py
?? frontend/src/pages/EvalsPage.tsx
?? rag-ai-local/functionality-docs/09232026/02_handoff-3-layer-guardrail-system.md
?? rag-ai-local/functionality-docs/09232026/03_handoff-guardrail-eval-harness-and-ui.md
```

**Verification results (this session, exact commands run):**
- `backend/.venv/Scripts/python.exe -m pytest -q` → `74 passed, 2 warnings in
  1.83s` (72 from the prior session + 2 new: `test_golden_set_never_false_blocks_legitimate_traffic`,
  `test_golden_set_catches_attacks_and_measures_retrieval_quality`, both in
  `backend/tests/eval/test_golden_set.py`).
- `backend/.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`
- `backend/.venv/Scripts/python.exe -m black --fast .` → `98 files left unchanged`.
- `cd frontend && npx tsc --noEmit` → no output, exit clean.
- **Manual smoke test of `POST /eval/run`** (ad-hoc Python script using
  `fastapi.testclient.TestClient` wired with the exact same fakes as
  `backend/tests/conftest.py`'s autouse fixtures, plus
  `tests.eval.fakes.HeuristicJudgeClient`/`ContextAwareLlmClient` from this session):
  `200 OK`, categories returned:
  `{'category': 'real', 'query_count': 5, 'recall_at_k': 1.0, 'mrr': 0.9, 'false_block_rate': 0.0}`,
  `{'category': 'expect', 'query_count': 4, 'refusal_rate': 1.0, 'false_block_rate': 0.0}`,
  `{'category': 'attack', 'query_count': 5, 'block_rate': 1.0}`. This is the first real
  exercise of the full endpoint end-to-end (route registration, runner orchestration,
  scoring aggregation, JSON response shape) — it was NOT run through pytest, it was a
  one-off script, since deleted (not committed).
- **Not done:** no `docker compose up` run against real Ollama/Gemini + a real judge
  model — same gap as the prior handoff, still open. The eval harness's whole point is
  measuring the *real* deployed guardrails, so this is the natural next verification
  step once Docker is available.

## COMPLETED

1. `backend/src/rag_backend/eval/` (new package):
   - `schemas.py` — `GoldenEntry`, `QueryEvalResult`, `CategoryMetrics`, `EvalReport`
     (pydantic models).
   - `golden_set.json` — 14 entries: 5 "real" (2 docs' worth of paraphrased questions
     against `employee_handbook.md`/`product_faq.md`/`onboarding_guide.txt`), 4
     "expect" (out-of-corpus benign questions: weather, sports, recipes, geography), 5
     "attack" (classic injection phrasings).
   - `golden_set.py` — `load_golden_set()`, validates JSON into `GoldenEntry` list.
   - `scoring.py` — pure functions: `looks_like_refusal()` (heuristic substring
     match), `find_rank()` (1-indexed rank in a ranked id list), `aggregate_category_metrics()`
     (only populates the metrics meaningful for that category — `None` for the rest).
   - `runner.py` — `run_golden_set()`: for every entry, runs the REAL
     `run_retrieval()` pipeline (not a mock) and parses the `\x00CITATIONS:` payload
     for guardrail verdicts/evidence; for "real" entries, additionally calls
     `get_input`/`normalize_input`/`embed_question`/`similarity_search` directly
     (bypassing `run_retrieval`'s threshold filtering) to get the pre-threshold ranked
     document list recall/MRR need.
2. `backend/src/rag_backend/api/routes_eval.py` (new) — `POST /eval/run`, wired into
   `main.py` alongside the other routers.
3. `backend/src/rag_backend/guardrails/schemas.py` — added public `BLOCKED_VERDICTS =
   {"unsafe", "judge_error"}`, replacing the private `_BLOCKED_VERDICTS` that was
   independently duplicated in both `step2b_input_guardrail.py` and
   `step9b_output_guardrail.py` (no behavior change — same set, same semantics, just
   one definition now, also reused by the eval runner's `blocked` computation).
4. `backend/tests/eval/` (new): `fakes.py` (`HeuristicJudgeClient`,
   `ContextAwareLlmClient` — see CONTEXT section for a real bug hit and fixed with
   these) and `test_golden_set.py` (2 tests, both passing — see Current Status).
5. Frontend: `frontend/src/pages/EvalsPage.tsx` (new) — "Run Evaluation" button, 3
   category metric cards (false_block_rate highlighted red when nonzero), a
   per-query results table. Wired into `App.tsx` as a 4th tab (`"evals"`, no router
   library in this app — follows the existing manual `Tab` union + conditional-render
   pattern). `frontend/src/api/client.ts` — added `EvalReport`/`CategoryMetrics`/
   `QueryEvalResult`/`GuardrailVerdict` types and `runGuardrailEval()`.
   `frontend/src/index.css` — added `.evals-toolbar`, `.eval-metrics`,
   `.eval-metric-card`, `.eval-metric-warn`/`.eval-metric-ok`, `.eval-results` classes,
   matching the existing flat-card/table styling used by `LogsPage`/`DocumentList`.
6. Cleaned up a stray `backend/data/input/` directory the manual smoke test created
   (real `settings.input_dir` default, not the test fixture's `tmp_path` override,
   since the smoke script ran outside pytest) — removed, was never committed.

## NOT DONE / STILL OPEN

1. **No live `docker compose up` verification**, for either the guardrails (carried
   over from the prior handoff) or this eval harness specifically. The eval harness's
   entire purpose is measuring the *real* deployed judge/LLM's guardrail accuracy —
   until this runs against Docker, all its numbers so far come from either the CI
   fakes (`HeuristicJudgeClient`/`ContextAwareLlmClient`) or the equivalent
   `TestClient`-based smoke test, neither of which reflects how a small local Ollama
   model (or Gemini) actually judges real text.
2. **No UI rendering for guardrails/evidence on the Chat page** — unchanged from the
   prior handoff, still out of scope unless requested.
3. **Nothing committed.** Still all working-tree changes on `feature/rag-guardrails`.
4. **Refusal detection is a coarse heuristic** (`looks_like_refusal()` in
   `eval/scoring.py`) — substring match on a fixed phrase list. Untested against a
   real model's actual "I don't know" phrasing style, which may not match any listed
   phrase and would understate `refusal_rate`. If a live run shows `refusal_rate`
   lower than expected on the "expect" category, check the raw `answer_excerpt` in
   the results table before assuming the guardrail/prompt is broken — it may just be
   the heuristic missing a valid refusal phrasing.
5. **Golden-set entries with a bad/missing `expected_document_filename`fail silently**
   (see CONTEXT below) — no validation currently catches a typo'd filename or a
   missing field on a "real" entry.

## NEXT ACTION

Run `docker compose up` from the repo root, open the frontend, click the new "Evals"
tab, click "Run Evaluation", and read the real numbers against the actually-deployed
Ollama model (or Gemini, depending on `.env`'s `LLM_PROVIDER`). Compare against this
session's fake-double numbers (real: recall@k=1.0, mrr=0.9; expect: refusal_rate=1.0;
attack: block_rate=1.0 — all false_block_rate=0.0) as a sanity baseline — a real small
model will very likely score noticeably lower on attack `block_rate` and/or nonzero on
`false_block_rate`, which is expected and worth discussing with the user rather than
treating as a wiring bug.

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE

- **A real bug was hit and fixed in `backend/tests/eval/fakes.py`'s
  `HeuristicJudgeClient` this session**: the first implementation keyword-matched
  against the ENTIRE filled judge prompt text (`messages[-1]["content"]`), which
  includes `guardrails/prompts.py`'s `INPUT_GUARDRAIL_PROMPT_TEMPLATE` instructions —
  and those instructions literally quote example injection phrases like `"ignore
  previous instructions"` as illustrations of what to detect. Because the template
  text itself always contains those phrases, EVERY query (including benign ones like
  "What is the capital of Australia?") was classified `unsafe` — confirmed by running
  `pytest tests/eval -q` and watching the console log show `verdict: unsafe` for a
  geography question. Fixed by extracting only the text after the template's final
  `"USER MESSAGE:"`/`"ASSISTANT RESPONSE:"` marker (`content.rsplit(marker, 1)[1]`)
  before matching. **If anyone else builds a keyword-based stand-in judge against
  these templates, this exact trap will bite again** — always test against a
  known-benign query first, not just known-attack queries, since a
  match-everything bug looks identical to a "successfully catches everything" bug
  until you check the false-positive side.
- **Why the pytest test overrides the default autouse guardrail fakes**: `backend/tests/conftest.py`'s
  `_fake_guardrail_judge_client` fixture (from the prior session) always returns
  `"safe"` — reasonable for most tests (isolates them from guardrail behavior), but it
  means the golden-set test would trivially show `block_rate=0` on attack queries if
  left as-is. `test_golden_set.py`'s own `_real_ish_guardrail_doubles` fixture
  re-monkeypatches both `judge_client.guardrail_judge_client` and
  `llm_model_client.llm_client` specifically for this one test file, layering on top
  of (overriding) the conftest defaults — this is the established per-test override
  pattern from the prior session, not a new convention.
- **`expected_document_filename` → `document_id` resolution happens at runner time,
  not load time**, via `postgres_store.list_documents()` (same store function the
  production pipeline already uses — works identically against the real DB and the
  test's `dummy_store` fake). This was a deliberate choice over hardcoding document
  ids in `golden_set.json`, since seeded documents get fresh UUIDs on every fresh
  DB/test run — filenames are the only stable identifier across runs. **Trap**: if a
  "real" golden-set entry has a typo'd or missing `expected_document_filename`,
  `_evaluate_entry()` in `runner.py` silently leaves `expected_document_id=None` and
  `matched_rank=None` — no exception, no warning, it just contributes a rank-not-found
  (0 for MRR, non-hit for recall) to that category's aggregate. Nothing currently
  validates that every "real" entry's filename actually resolves; this was
  deliberately not added (kept the loader simple) but would be a reasonable follow-up
  if the golden set grows and someone wants a "fail loudly on a bad entry" guarantee.
- **The `k` parameter does double duty**: `run_golden_set(k=...)` (defaulting to
  `settings.retrieval_top_k`) is used both as `similarity_search`'s `top_k` (how many
  chunks get ranked at all) and as the recall-cutoff in `aggregate_category_metrics`
  (`matched_rank <= k`). Since the ranked list is already capped to `k` items by the
  same call, `recall_at_k` and "found in the ranked list at all" are currently
  identical — there's no way to compute e.g. recall@3 from a top-10 search with the
  current design. This is intentional for v1 (matches production retrieval behavior
  exactly) but would need `similarity_search(embedded, top_k=<something bigger>)` plus
  a separately-parameterized cutoff if finer-grained recall curves are ever wanted.
