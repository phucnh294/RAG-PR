---
title: Agents Testing Pipeline — Agents Tab, File-Based Agent Handoff and Test Evidence (PR from feature/testing-agents into master)
date: 2026-09-26
type: session-handoff
area: agents-testing-pipeline
status: in-progress
session_id: d288aa3b-88a9-4349-9428-ba1fad409379
tags: [agents, testing, playwright, vision-model, ollama, handoff, evidence, backend, frontend, docker]
keywords: [feature/testing-agents, agents/agents-result, handoff.py, handoff_render.py, handoff-json, AGENTS_RESULT_DIR, AgentHandoffError, read_output, page_messages, ExecutionEvidence, step6_test_automation, step7_test_validation, qwen2.5vl:3b, VISION_PROVIDER, test-runner, myweb, live_handoff_check.py, taskfeae4e79]
supersedes: 09252026/08_handoff-semantic-cache-conversation-memory.md
related: [09252026/09_agents-testing-pipeline-design.md]
next_action: Get the feature/testing-agents PR reviewed and merged, then start one full Agents run from the Agents tab (local Ollama models, ~1 h+) and check that every agents/agents-result/{agent}/ folder gets its input/output files and the tab shows the test case results with screenshots.
---

## TL;DR
- **What:** the Agents feature, on branch `feature/testing-agents`. The branch starts from `6f2b8f9`, which is already in `origin/master` through PR #16. The feature has five parts:
  - a new **Agents** tab;
  - three containers: `vision-model` (Ollama `qwen2.5vl:3b`), `test-runner` (Playwright/Chromium) and `myweb` (the Register Account page at http://localhost:8080/myweb);
  - a seven-step agent pipeline: capture → UI analysis → business rules → test design → business confirmation → Playwright automation → test validation;
  - file-based handoff, where each agent writes `agents/agents-result/{agent}/{input,output}/{agent}_task{id}_{datetime}.md` and the next agent's input is parsed back from those files;
  - per-step test evidence: a screenshot, the message shown on the page, and the observed value.
- **Why:** the user wanted to watch how testing agents work. They asked for each agent's input and output logged carefully, the output of one agent to be the input of the next, and proof (images and messages) that each test case passed or failed.
- **Where:**
  - backend: `backend/src/rag_backend/agents/`, `api/routes_agents.py`, `schemas/agents.py`;
  - frontend: `AgentsPage`, `AgentStepCard`, `AgentReport`, `RunFileLink`;
  - new top-level folders: `test-runner/`, `myweb/`, `vision-model/`;
  - `docker-compose.yml`;
  - the design doc `09252026/09_agents-testing-pipeline-design.md`.
- **Impact:**
  - 274/274 backend tests pass (all agents tests included); ruff, black and mypy are clean; the frontend builds; the test-runner has 11/11 real-Chromium tests passing.
  - A live partial run (`feae4e79`) executed two cases in the real browser: TC-REG-001 ✅ and TC-REG-002 ❌ (it expected the wrong text on purpose). The local model then wrote the validation file in 439 s and correctly classified the failure as a `test_defect`.

## Current Status
- **Code:** complete and verified. It is committed on `feature/testing-agents` and a PR is open against `master`. The PR holds only this work, because the base `6f2b8f9` is already merged (PR #16).
- **Tests** (run on 2026-09-26):
  - `backend/.venv/Scripts/python -m pytest -q` → **274 passed** (55.5 s);
  - `ruff check .` → all checks passed; `black --check .` → 195 files unchanged; `mypy src` → no issues in 122 files;
  - `docker compose run --rm test-runner python -m pytest -q` → **11 passed** (101 s);
  - `npm run build` (frontend) → OK.
- **Live stack:** `backend` and `frontend` are rebuilt from this tree and running. `.env` has `VISION_PROVIDER=ollama` and `VISION_MODEL_NAME=qwen2.5vl:3b`. The agents text model falls back to the vision model.
- **Never done:** a full seven-agent run from the Agents tab with the handoff layout. The earlier full local run `92cc24d2` predates the handoff layout and died at step 7 on truncation; that was fixed afterwards.

## COMPLETED
- **Pipeline** (`agents/pipeline.py`, `step1_capture.py` … `step7_test_validation.py`):
  - each step logs its input, output, checks and every LLM attempt into `run.json`;
  - rejected cases loop back to test design for up to `AGENTS_MAX_DESIGN_ROUNDS` rounds;
  - only one run executes at a time; a run left over from a backend restart is reported as `stale`.
- **File-based handoff** (`agents/handoff.py`, `agents/handoff_render.py`):
  - `AgentContext.begin` writes the input `.md` and `finish` writes the output `.md`;
  - `pipeline.py` builds each next input with `handoff.read_output(record, step, Model)`;
  - failed steps still get an output file with `❌ FAILED`;
  - referenced PNG and spec files are copied into `{stem}_files/` next to the output file;
  - sources are listed in every input file.
- **Evidence:**
  - the test-runner records `page_messages` (visible `[role=alert|status]` and `[aria-live]` text), `observed` and a full-page screenshot after every executed step;
  - the test-automation output shows a table per case plus every screenshot;
  - the test-validation output shows each case as ✅/❌, with its proof screenshot embedded;
  - the run folder keeps `test-cases/{id}/test-case.md`, `result.json` and `evidence/`.
- **API:** `GET /agents/runs/{id}/handoff/{path}` serves only paths recorded in that run and checks ownership; `GET /agents/runs/{id}/artifacts/{path}` serves the run folder.
- **UI:**
  - every step card has input.md / output.md buttons and lists its sources;
  - `ExecutionEvidence` ("Test case results — X/Y passed") appears as soon as step 6 has output. It no longer waits for step 7's report; that gate was the bug behind "I don't see the test case result with the evidence".
- **Docs:** the design doc (v2), `CLAUDE.md`, `.env.example`, `.claude/rules/file-organization.md` (Rule 0 exception for `agents/agents-result/**`), `.claude/agents/business-analysis.md` and `test-validation.md`.

## NOT DONE / STILL OPEN
1. **No full end-to-end run with the new layout.** Only the partial live check `feae4e79` exists, created by `live_handoff_check.py` in the session scratchpad. In it, steps 3–5 were canned files, and steps 6 and 7 ran for real from those files.
2. **The Gemini path is unverified since the latest changes.** Removing `maxOutputTokens` and adding `fail_on_truncation` for Gemini was never confirmed live, because the free-tier quota was exhausted (429). See `backend/src/rag_backend/llm_model/client.py` `_google_generation_config`.
3. **Local models are slow on this CPU.** Prompts run at about 7 tokens/s and generation at about 2.3 tokens/s. A full run takes more than 1 h, and step 7 alone took 439 s for 2 cases. Timeouts are 1800 s (`VISION_REQUEST_TIMEOUT_SECONDS`, `AGENTS_LLM_TIMEOUT_SECONDS`).
4. **The live-check runs** (`b1eb3375`, `feae4e79`) were created as user id `live-check`, so only admins see them in the Agents tab. They can be deleted from `backend/pipeline-logs/agents/` and `agents/agents-result/` at any time.
5. **A cosmetic issue in input files:** the header shows `Status | running`, the status when the file was written (`handoff_render.py` `render_handoff`, the header table). It could be relabelled "Status when written".
6. **Missing files the rules point to:** `must-read.md` and `rag-ai-local/template/` (with its templates) do not exist, although `.claude/rules/file-organization.md` and `CLAUDE.md` reference them. The docs follow the structure of sibling docs instead.

## NEXT ACTION
Merge the PR, then run the full pipeline once from the UI:
```
docker compose up -d --build
# open http://localhost:5173 → Agents tab → Run (default requirement + http://myweb:8080/myweb/)
# after it finishes:
ls agents/agents-result/*/output/
```
Expect one output file per agent, including `_r2` design and confirmation files if cases were rejected. Also expect a "Test case results" section with screenshots in the tab.

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE
- **The handoff is real, not a log copy.** The user asked that "the output will be the input for the next agent". `pipeline.py` therefore throws away each step's return value and re-reads the output `.md` from disk.
  - `test_next_agent_input_is_parsed_from_the_previous_output_file` edits a file mid-run to prove it.
  - Don't "optimise" this back to in-memory passing.
- **User decisions:**
  - the result folder lives at the repo root `agents/agents-result/`, not under pipeline-logs;
  - `{id}` is the first 8 characters of the run id;
  - the per-step JSON mirror (`agents/NN_step/*.json`) was dropped; `run.json` keeps everything;
  - myweb is its own container;
  - the LLM writes structured JSON steps and a deterministic runner executes them; free-form LLM code is never run;
  - the requirement text comes from the Agents tab.
- **The provider history is not in the code.**
  - The user first switched vision to Google Gemini (same API key, `gemini-flash-latest`), then back to "ollama model in docker for text and vision".
  - `VISION_PROVIDER` defaults to `ollama` independently of `LLM_PROVIDER=google`, which chat still uses. An earlier fallback let `LLM_PROVIDER=google` hijack vision.
- **Traps already hit:**
  - Gemini returned objects where strings were expected until `responseJsonSchema` was sent.
  - Gemini thinking tokens count against `maxOutputTokens`, which truncated answers.
  - The local model timed out at 600 s in step 2 until the vision image was downscaled to 640 px and the JSON compacted.
  - Step 7 truncated (`done_reason=length`) when it received full results; it now gets one compact line per case.
  - A Python edit once wrote cp1252 bytes into `config.py`, so always write with `encoding="utf-8"`.
  - In Git Bash, `docker compose exec` paths need `MSYS_NO_PATHCONV=1`.
- **Ground truth for evidence:** `agents/agents-result/test-automation/output/test-automation_taskfeae4e79_20260927-013034_files/test-cases/TC-REG-002/evidence/step-03-expect_text.png` was checked visually. It shows "First name is required." under the field, matching `observed text='First name is required.'`.
- **Security:** never print `GOOGLE_API_KEY` from `.env`; only check that it is present. The SSRF guard is `AGENTS_ALLOWED_TARGET_HOSTS=["myweb"]`, and every `goto` step is pinned to the target host.
