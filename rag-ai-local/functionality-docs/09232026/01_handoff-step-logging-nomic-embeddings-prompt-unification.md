---
title: RAG Pipeline Session Handoff — Step Input/Output Logging, Real Embeddings, Prompt Unification
date: 2026-09-23
type: session-handoff
area: rag-pipeline
status: in-progress
session_id: n/a
tags: [rag, embeddings, ollama, nomic-embed-text, logging, retrieval, hallucination, handoff]
keywords: [StepRecorder, embed_texts, /api/embed, search_document:, search_query:, min_similarity_score, build_prompt, SYSTEM_PROMPT_TEMPLATE, PR #7]
related: [09222026/01_handoff-postgres-persistence-pipeline-logs-mobile-ui.md, 09172026/01_rag-pipeline-implementation-plan.md, 09172026/02_rag-pipeline-project-structure.md]
next_action: "None queued. Pull master locally (git checkout master && git pull) before starting new work — local master is currently 4 commits behind origin/master."
supersedes: 09222026/01_handoff-postgres-persistence-pipeline-logs-mobile-ui.md
---

## TL;DR
- **What:** Branch `fix/rag-retrieval` (3 commits) was completed, pushed, opened as PR #7, and **merged to `master`** on GitHub. It added exact-template step-by-step input/output logging for both pipelines, replaced the hash-based embedding stub with real `nomic-embed-text` served from a new dedicated `embedding-model` container, and made one small edit to the retrieval system prompt.
- **Why:** The user wanted to verify the pipeline end-to-end from logs, wanted real semantic embeddings instead of a bag-of-words stub, and — after a hallucination bug was diagnosed then explicitly cancelled earlier, then revisited — asked to change the no-context system prompt. The final direction taken was **not** a deterministic code-level guardrail; see CONTEXT section below for why that matters.
- **Where:** `backend/src/rag_backend/pipeline_logging.py` (`StepRecorder`), both `rag_pipeline/{indexing,retrieval}/pipeline.py` orchestrators, `backend/src/rag_backend/embedding_model/` (`client.py` rewritten async, `fake_client.py` new), `embedding-model/` (new Docker service), `backend/src/rag_backend/rag_pipeline/retrieval/step8_build_prompt.py`.
- **Impact:** Every one of the 18 pipeline steps (8 indexing + 10 retrieval) now logs its real input and output to both console and the per-run JSON file. Embeddings are real (nomic-embed-text, 768-dim) and persisted to Postgres. The retrieval system prompt is now a single template regardless of whether any chunk matched — **the LLM alone decides** whether to say "I don't know," there is no code-level short-circuit. `master` is fully up to date with all of this (`7ade4fb`).

## Current Status

- **Branch:** local checkout is still on `fix/rag-retrieval` (`017a62a`), which is identical to `origin/master` minus the merge commit. **Local `master` branch is 4 commits behind `origin/master`** (`91d4999` vs `7ade4fb`) — nobody has run `git checkout master && git pull` yet this session.
- **Backend tests:** 49/49 passing — `cd backend && source .venv/Scripts/activate && pytest -q`.
- **Lint/type-check:** `ruff check src tests`, `black --check src tests`, `mypy src` all clean as of `017a62a`.
- **Docker state:** all five services (`postgres`, `llm-model`, `embedding-model`, `backend`, `frontend`) up and healthy, rebuilt from `017a62a`.
- **GitHub PRs:** #1–#7 all **MERGED**. No open PR right now.
- **git status:** one uncommitted change on `fix/rag-retrieval` at handoff time — this doc's predecessor's `status:` field being flipped to `superseded` (housekeeping only, not code).

## COMPLETED

1. **Step-by-step input/output logging (`34b2a13`).** New `StepRecorder` class in `pipeline_logging.py`: `log_input(step, data)` / `log_output(step, data)`, each emitting a console line in the exact template `"{Process Name} - {step} {ISO timestamp} - input|output: {data}"` and writing into the JSON record's `steps[step_name]` (`input`, `input_at`, `output`, `output_at`, `duration_ms`). Both `retrieval/pipeline.py` (10 steps) and `indexing/pipeline.py` (8 steps) rewritten to call `steps.log_input(...)`/`steps.log_output(...)` around every single step — not just timing, the actual data flowing through. A step that raises leaves an "input" entry with no "output," visibly marking the failure point in the JSON. Verified live via `docker logs`, grepping for `"Indexing - "` / `"Retrieval - "`, confirming all 18 steps hit the exact template with real data.
   - **Bug caught and fixed during this work:** `raw_query.message` doesn't exist on the `RawQuery` dataclass — the field is `raw_query.text`. Caught immediately by the test suite (`AttributeError`), fixed before it reached a commit.
2. **Real `nomic-embed-text` embeddings (`eda4338`).** New dedicated `embedding-model/` Docker service (Ollama, mirrors `llm-model/`'s shape, pulls `${EMBEDDING_MODEL_NAME:-nomic-embed-text}`). `embedding_model/client.py` rewritten as an async httpx client hitting Ollama's batched `POST /api/embed`. Nomic's task-prefix convention applied at the call sites (not inside the generic client): `"search_document: "` in `indexing/step6_embedding.py`, `"search_query: "` in `retrieval/step3_embedding_question.py`. Old hash-stub logic preserved as `embedding_model/fake_client.py` (test-only, matches the existing `dummy_store`/`postgres_store` split pattern) — a new autouse fixture in `conftest.py` monkeypatches the module-level `embedding_client` singleton to this fake for every test.
   - **`min_similarity_score` raised 0.5 → 0.7 based on live measurement**, not guesswork: after dropping the stale (pre-nomic) Postgres volume and re-seeding, a true match scored ~0.91 while two genuinely unrelated seeded documents scored 0.60 and 0.62 for the same query — both would have false-positived past a 0.5 threshold. 0.7 sits comfortably above the observed noise ceiling and below the true-match score. Documented in `config.py`'s comment and `README.md`'s Current Limitations section as based on only 3 seeded documents — not rigorously tuned, worth revisiting with more/varied documents.
3. **Retrieval system prompt unified (`017a62a`).** `step8_build_prompt.py`'s separate `SYSTEM_PROMPT_NO_CONTEXT` branch was removed. `build_prompt` now always returns the same `SYSTEM_PROMPT_TEMPLATE.format(context=...)` shape (with `context_text` simply empty when nothing matched) and the pipeline always calls the LLM — there is no code path that skips the LLM call or answers deterministically. This directly reverses an in-progress guardrail I had built earlier in this session (see CONTEXT section — important, do not silently re-add it).
4. **PR #7 opened and merged.** Bundled all three commits above into `https://github.com/phucnh294/RAG-PR/pull/7`, merged into `master` (now at `7ade4fb`) on GitHub.

## NOT DONE / STILL OPEN

1. **Local `master` branch is stale** (`91d4999`, 4 commits behind `origin/master`'s `7ade4fb`). Nobody has pulled it this session. Not a blocker, but the very next session should `git checkout master && git pull` before branching off it again.
2. **The original hallucination bug (business rule 5) is arguably still open, by design.** The retrieval pipeline will call the LLM even when zero chunks clear `min_similarity_score`, trusting the model to say "I don't know" rather than enforcing it in code. This was a deliberate user decision this session — see CONTEXT section for the full sequence, since it reverses something I had already built and tested. If the LLM (currently `qwen2.5:0.5b-instruct`, a very small model) hallucinates again in this configuration, that is expected/known behavior right now, not a regression to silently "fix" by re-adding the removed guardrail without asking first.
3. **Architecture docs still out of sync with the code** (carried over from prior handoffs, still unaddressed): `rag-ai-local/functionality-docs/09172026/02_rag-pipeline-project-structure.md` describes indexing as 6 steps / retrieval as 5 steps; actual code has 8 and 10.
4. **No bulk re-index tool** for documents embedded before the nomic-embed-text switch — carried over, documented in `README.md`.
5. **PDF parsing still unimplemented** (`step2_document_parsing.py` raises `PdfParsingNotImplementedError`).
6. **`rag-ai-local/template/` still does not exist**, despite being referenced by `CLAUDE.md`, `.claude/rules/file-organization.md`, and the handoff/functionality-doc skills. This doc was hand-structured again, same as the last two handoffs, since there is nothing to literally copy.

## NEXT ACTION

No task is currently queued — wait for the user's next instruction. When a new feature branch starts, first sync local `master`:

```bash
cd "D:/AI/CLAUDE/RAG" && git checkout master && git pull origin master
```

Then branch from that (never work directly on `master`), per this repo's established branch-per-feature workflow.

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE

- **The no-context guardrail was built, tested, and verified live earlier this session — then explicitly reverted by the user, in the same session, via direct hand-edits to the file rather than a request to me.** Sequence: (1) I implemented a deterministic short-circuit — `build_prompt` returned `None` when `context.citations` was empty, and `pipeline.py` skipped `call_llm_model` entirely, yielding a fixed `NO_CONTEXT_ANSWER` string instead. This was tested (including a test whose fake LLM client raises `AssertionError` if ever called, to prove the LLM path was truly skipped), verified with 51 passing tests, and rebuilt live in Docker. (2) The user then edited `step8_build_prompt.py` directly in their IDE twice, each time removing more of that guardrail (first the early-return guard, then the `NO_CONTEXT_ANSWER` constant itself), while separately asking me to "compose docker again." (3) When I moved to restore what looked like accidental deletions (breaking `pipeline.py`'s import), the user stopped me and said explicitly: **"dont modified what i changed, I want it will be judge by llm model not by manual, just fix it if it have exception or error."** This was a deliberate reversal of my approach, not an accident — the user wants the LLM itself to decide/judge the no-context case via prompt instructions, not a hard-coded rule. I fixed only the resulting breakage (the dangling `NO_CONTEXT_ANSWER` import/branch in `pipeline.py`, and the tests that asserted the old deterministic behavior) without reintroducing the guard. **Do not re-add the deterministic short-circuit unless the user asks again** — this exact approach was tried and explicitly rejected in favor of trusting the LLM.
- **Why this matters for future hallucination bug reports:** if the user (or a future session) reports the LLM still answering confidently with no real context, the "obvious" fix (skip the LLM, answer deterministically) has already been built once and taken back out on purpose. Point this out and ask before re-implementing it — the user may want a different mitigation (e.g., a stronger/larger LLM model, as they floated earlier this session, or prompt wording tuning) rather than a code-level rule.
- **PR #7 was merged without an explicit "merge it" instruction being given to me in this visible session** — the last message I sent said "Let me know if you want it merged," and the very next observation was that PR #7 already showed `MERGED` on GitHub when checked via `gh pr view`. The user must have merged it themselves via the GitHub UI or `gh` outside this conversation. Don't assume every merge in this repo's history necessarily came through an explicit chat request — check `gh pr view <n> --json state,mergedAt` rather than assuming from chat history alone.
- **Docker rebuilds are still required after every code change** — no hot-reload is wired into `docker-compose.yml`. This session rebuilt `backend` (and once, all services) via `docker compose up -d --build [service]` after each of the three commits' worth of changes; skipping this step and testing against a stale container remains an easy mistake (flagged in the prior handoff too — still true).
- **The embedding client test fixture pattern is now used in three places in this codebase** (`llm_client`, `postgres_store`, `embedding_client`) — all via the same "module-attribute lookup at call time" trick (`from X import Y as module_ref`, call `module_ref.singleton.method()`) so `monkeypatch.setattr(module, "singleton", fake)` works. If a new external client is added, follow this exact pattern, not a default-parameter injection (which binds at def-time and can't be monkeypatched after the fact).
