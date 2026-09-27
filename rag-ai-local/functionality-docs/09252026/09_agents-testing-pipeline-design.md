---
title: Agents Tab — Vision/LLM UI Test-Generation Pipeline with Per-Step Input/Output Logging
date: 2026-09-25
type: functionality
area: agents-testing-pipeline
status: implementation-complete
session_id: d288aa3b-88a9-4349-9428-ba1fad409379
tags: [agents, testing, playwright, vision-model, ollama, logging, backend, frontend, docker]
keywords: [agents-result, handoff.py, handoff-json, AGENTS_RESULT_DIR, AgentHandoffError, page_messages, read_output, run.json, test-case.md, evidence, observed, run_layout, CaseLedger, AGENTS_CAPTURE_EVIDENCE, qwen2.5vl:3b, gemini-flash-latest, VISION_GOOGLE_MODEL_NAME, responseJsonSchema, MAX_TOKENS, fail_on_truncation, agents_transient_retries, vision-model, test-runner, myweb, "/capture", "/run", step1_capture, step2_ui_analysis, step3_business_rules, step4_test_design, step5_business_confirmation, step6_test_automation, step7_test_validation, call_structured, llm_calls, AgentOutputValidationError, TestRunnerError, AgentTargetNotAllowedError, AGENTS_ALLOWED_TARGET_HOSTS, VISION_PROVIDER, AGENTS_LLM_MODEL_NAME, AGENTS_NUM_CTX, AGENTS_MAX_DESIGN_ROUNDS, render_spec_ts, suggested_locator, pipeline-logs/agents, "/agents/runs"]
files:
  - docker-compose.yml
  - vision-model/Dockerfile
  - vision-model/entrypoint.sh
  - test-runner/server.py
  - test-runner/runner.py
  - test-runner/models.py
  - test-runner/tests/test_runner.py
  - myweb/site/myweb/index.html
  - myweb/site/myweb/app.js
  - backend/src/rag_backend/agents/pipeline.py
  - backend/src/rag_backend/agents/schemas.py
  - backend/src/rag_backend/agents/llm_json.py
  - backend/src/rag_backend/agents/checks.py
  - backend/src/rag_backend/agents/locators.py
  - backend/src/rag_backend/agents/prompts.py
  - backend/src/rag_backend/agents/defaults.py
  - backend/src/rag_backend/agents/run_store.py
  - backend/src/rag_backend/agents/handoff.py
  - backend/src/rag_backend/agents/handoff_render.py
  - backend/src/rag_backend/agents/spec_render.py
  - backend/src/rag_backend/agents/step1_capture.py … step7_test_validation.py
  - backend/src/rag_backend/api/routes_agents.py
  - backend/src/rag_backend/llm_model/client.py
  - backend/src/rag_backend/pipeline_logging.py
  - backend/src/rag_backend/agents/clients.py
  - backend/src/rag_backend/agents/run_layout.py
  - backend/src/rag_backend/agents/run_files.py
  - backend/src/rag_backend/agents/test_case_docs.py
  - frontend/src/pages/AgentsPage.tsx
  - frontend/src/components/AgentStepCard.tsx
  - frontend/src/components/AgentReport.tsx
  - .claude/agents/business-analysis.md
  - .claude/agents/test-validation.md
version: 2
last_updated: 2026-09-26
extraction_method: written-during-implementation
related_docs: [09252026/07_semantic-cache-conversation-memory-design.md]
---

## TL;DR
- **What:** a new **Agents** tab runs a seven-step UI test-generation pipeline against a Register Account page (`myweb`). The steps are:
  1. page capture;
  2. UI analysis by a vision model: local `qwen2.5vl:3b` by default, or Gemini (`gemini-flash-latest`) when `VISION_PROVIDER=google`;
  3. business rules taken from requirement text;
  4. test design;
  5. business confirmation, where rejected cases loop back to step 4;
  6. Playwright execution;
  7. a validation report.

  Each step records its exact **input**, **output**, every LLM attempt, and deterministic contract checks.
  Agents hand over through files: each agent writes `agents/agents-result/{agent}/{input,output}/{agent}_task{id}_{datetime}.md`, and the next agent's input is parsed back from those output files.
- **Why:** to show how multi-agent test generation behaves. Each agent must receive the correct input and return the expected output, and when that fails, the log must show which step went wrong and why.
- **Where:**
  - three new containers: `vision-model`, `test-runner` and `myweb`;
  - the backend package `rag_backend/agents/` and the route `routes_agents.py`;
  - the `LlmClient` now supports images and JSON schemas;
  - `StepRecorder` gained status, extras and atomic writes;
  - the frontend has `AgentsPage` plus an `agents` filter in the Logs tab.
- **Impact:**
  - one click produces an audited run: a chain of per-agent Markdown handoff files in `agents/agents-result/`, plus `backend/pipeline-logs/agents/{ts}_{run_id}/` with `run.json`, test-case docs and per-step screenshots that show the message the page displayed;
  - the backend suite is 274 tests;
  - the test-runner suite has 11 real-Chromium tests against myweb, including the per-step evidence and page messages.

## What the Agents pipeline does, step by step

The orchestrator is `rag_backend/agents/pipeline.py::run_agents_pipeline`. It runs in a FastAPI background task, one run at a time.

| Step key | Actor | Input logged | Output logged |
|---|---|---|---|
| `step1_capture` | test-runner `/capture` | `target_url` | title, final URL, screenshot ArtifactRef, aria snapshot, DOM elements with `suggested_locator` |
| `step2_ui_analysis` | vision model (screenshot + DOM) | screenshot ref, DOM elements, aria snapshot | `UiAnalysis`: elements, locators, required flags, messages |
| `step3_business_rules` | text model | requirement text + UI analysis | `BusinessRules` (`BR-001`…, each with a `source_quote`) |
| `step4_test_design[_rN]` | text model | rules + UI analysis + feedback from rejections | `TestDesign`: cases written as a step DSL (`goto/fill/click/expect_*`) |
| `step5_business_confirmation[_rN]` | text model | rules + cases | a verdict per case; uncovered rules recomputed by code |
| `step6_test_automation` | spec renderer + test-runner `/run` | approved cases, base URL | per-case/per-step results, failure screenshots, `.spec.ts` ArtifactRef |
| `step7_test_validation` | code metrics + text model | rules, cases, results, metrics | `ValidationReport`: counts and coverage from code, summary and failure cause from the LLM |

The steps are chained by the validated pydantic models, not by raw text. So in the log, `steps.stepN.input` equals `steps.stepN-1.output`, and `tests/agents/test_pipeline.py::test_output_of_each_agent_is_the_input_of_the_next` asserts exactly that.

## Agent handoff files: each agent's output file is the next agent's input

Every Agents pipeline agent has its own folder in `agents/agents-result/` (setting `AGENTS_RESULT_DIR`, bind-mounted into the backend at `/app/agents-result`). The logic lives in `agents/handoff.py` and `agents/handoff_render.py`.

```
agents/agents-result/
  page-capture/       input/page-capture_task1a2b3c4d_20260926-101530.md
                      output/page-capture_task1a2b3c4d_20260926-101534.md  (+ ..._files/capture/*.png)
  ui-analysis/        input/ … output/ …
  business-analysis/  input/ … output/ …   rule extraction AND case confirmation, every round
  test-design/        input/ … output/ …   one pair per design round
  test-automation/    input/ … output/ …   (+ ..._files/test-cases/{id}/evidence/*.png, automation/*.spec.ts)
  test-validation/    input/ … output/ …   the final result
```

- **Name format:** `{agent}_task{id}_{datetime}.md`. `{id}` is the first 8 characters of the run id (as the UI shows it); the datetime is UTC `YYYYMMDD-HHMMSS`, with a `-2` suffix when two files of one agent land in the same second.
- **Each file has two parts.**
  - A readable part: a header table (agent, step, run id, status, time); for inputs, **Sources**, which links the earlier output files the input was built from; for outputs, a `## Result: ✅ SUCCESS — …` / `❌ FAILED — …` line, a summary, the contract checks and a model-call table.
  - A `<!-- handoff-json -->` fenced JSON block holding the exact payload.
- **The handoff is real.** `pipeline.py` never passes one step's return value to the next. After every step it calls `handoff.read_output(...)`, which parses the JSON block back from disk and validates it against the pydantic contract. Test-automation's executed cases are read from its own input file for test-validation. `test_next_agent_input_is_parsed_from_the_previous_output_file` edits a business-analysis output file mid-run and asserts that test design received the edited rule.
- **A failed step still writes its output file.** `AgentContext.fail` writes it with `❌ FAILED` and the error, keeping the file name, so the chain on disk shows where it stopped. A corrupt or missing file raises `AgentHandoffError` and stops the run; the pipeline does not guess.
- **Every executed test step captures what the user saw.**
  - The test-runner records `page_messages`: the text of every visible `[role=alert]`, `[role=status]` and `[aria-live]` element right after the step, for example `firstName-error: First name is required.` or `success-banner: Account 123 has been created successfully!`.
  - The test-automation output has one section per case: a step table (Result ✅/❌ | Message shown on page | Observed | Error | screenshot link), then every step's screenshot embedded.
  - The test-validation output lists every case as ✅/❌; a failure shows the failing step, its expected value, the message the page actually showed and a link to its screenshot.
- **Output attachments.** Files an output references are copied into `{file stem}_files/` next to it, so each `.md` renders on its own. The API serves handoff files only through `GET /agents/runs/{id}/handoff/{path}`, and only paths recorded in that run's `steps[*].handoff`. The Agents tab shows input.md / output.md buttons and the source files on every step card.

## Run folder layout: run record, README, test cases and evidence

The run record and test evidence stay in one folder per run, laid out by `agents/run_layout.py`:

```
backend/pipeline-logs/agents/{timestamp}_{run_id}/
  run.json            full record, including every LLM prompt and raw response (the Agents and Logs tabs read this)
  README.md           summary: status, models, a step table naming each agent's input/output file, test-case table, report
  capture/            capture.png · capture_vision.png
  automation/         Register_Account.spec.ts
  test-cases/
    TC-REG-001/
      test-case.md     rules covered, business verdict, data, a step table with result + message shown on page + observed + screenshot link, expected vs actual, failure analysis
      result.json      raw execution result
      evidence/        step-01-goto.png, step-02-fill.png, ... one screenshot per executed step
```

- **The old per-step JSON mirror is gone.** The earlier `agents/NN_step/{input,output,checks}.json` and `llm_calls/` files were replaced by the handoff Markdown files; their data is still complete in `run.json`.
- **Test case files grow as the case moves through the pipeline.** `test_case_docs.CaseLedger` writes each case's files after test design, rewrites them after business confirmation and again after execution, and adds the failure analysis after validation.
  - A case the business agent rejected still gets a `test-case.md` that says "Not executed — rejected by the business agent."
- **Evidence proves why a case passed or failed.** After every executed step, the test-runner takes a full-page screenshot and records `observed`: what the page actually showed.
  - `goto` / `expect_url` record the URL; `fill` / `expect_value` the field value; `expect_text` the element's text; `click` / `expect_visible` / `expect_hidden` its visibility.
  - Example from the live check: expected "First name is mandatory.", observed `text='First name is required.'`, with the screenshot showing that message under the field.
  - The failing step's screenshot is also the case's failure screenshot.
- **The API serves any file of the folder.** `GET /agents/runs/{id}/artifacts/{path}` accepts `.png/.md/.json/.ts/.txt`. The path is validated segment by segment and must resolve inside the run folder.
- **Old runs still work.** Runs from before this layout (a flat `agents/{stem}.json` plus `agents/artifacts/{id}/`) are still listed and readable.

## How every agent call is logged and validated

Every LLM-backed step goes through `agents/llm_json.py::call_structured`. Each attempt is appended to `steps[step].llm_calls` with these fields:
- `attempt`
- `provider`
- `model`
- `response_format`
- `messages` (the exact prompt; images are replaced by `<image png N bytes sha256=…>`)
- `raw_response`
- `parse_error` / `validation_errors`
- `valid`
- `duration_ms`

For Ollama, the pydantic JSON schema is sent as `format`, which constrains decoding. If the output is still invalid, one repair attempt feeds the model its own answer plus the validation errors. If both attempts fail, `AgentOutputValidationError` fails the step.

After schema validation, `agents/checks.py` runs **content checks** against facts the pipeline already has:
- **UI analysis:** every "observed" element's locator matches a captured DOM element, and required flags agree with the DOM.
- **Business rules:** every `source_quote` appears verbatim in the requirement (a hallucination guard), and each `field` exists in the UI.
- **Test design:** cited rule ids exist, locators resolve against the DOM, and every rule is covered.
- **Confirmation:** there is a verdict for every case and no unknown ids.
- **Validation:** the counts add up, there are no invented failures, and every failure is explained.

Checks with severity `error` stop the run. Checks with severity `warning` are only logged.

The run record is rewritten after every step and every LLM call, using an atomic tmp-then-replace write in `pipeline_logging._write_json`. The Agents tab polls it every 2 s.

## Key decisions and rejected alternatives

- **The LLM writes a JSON step DSL, not Playwright code.** Letting a 3B model write free-form `.spec.ts` was rejected: small models produce code that doesn't compile, and executing LLM-written code is a code-injection path. `test-runner/runner.py` interprets the DSL, and `spec_render.py` deterministically renders the same steps as a readable `.spec.ts` artifact.
- **Playwright runs in its own `test-runner` container, not in the backend.** This keeps about 1 GB of Chromium out of the backend image. It also means the browser, which visits pages chosen by users, lives in a process with no DB credentials or `GOOGLE_API_KEY`.
- **SSRF guard.** Targets are limited to `AGENTS_ALLOWED_TARGET_HOSTS` (default `["myweb"]`). Any `goto` a test case points at another host is rewritten to the target page and flagged by the `gotos_on_target` check.
- **`suggested_locator` is computed by code in step 1.** It is given to the vision agent, which confirms or annotates it rather than inventing locators. Priority is label > role+name > testid > `#id`, as in `.claude/agents/ui-analysis.md`.
- **Metrics come from code; the LLM only writes the narrative.** Pass rate and rule coverage in step 7 never come from the model.
- **Rejection loop.** Rejected cases and uncovered rules go back to test design, up to `AGENTS_MAX_DESIGN_ROUNDS` (default 2), under their own `_r2` step keys so each round's input and output stay separate. Cases still rejected after the last round are reported under `dropped_cases` and never executed.
- **myweb is static nginx with `novalidate` and `role="alert"` messages.** Native browser validation bubbles can't be asserted from the DOM. The account number is `123 + localStorage counter`, so a fresh browser context always sees "Account 123", which keeps tests deterministic.

## Configuration of the Agents pipeline

The settings live in `config.py` and are documented in `.env.example`.

- **`VISION_PROVIDER`** (default `ollama`): **independent of `LLM_PROVIDER`**. `google` sends the agents to Gemini, using the same `GOOGLE_API_KEY` as chat.
- **`VISION_GOOGLE_MODEL_NAME`** (default `gemini-flash-latest`): the Gemini model for the agents. It is deliberately separate from `GOOGLE_MODEL_NAME`, so chat can stay on `gemini-flash-lite-latest`. The text agents use the same model unless `AGENTS_LLM_MODEL_NAME` is set.
- **`AGENTS_CAPTURE_EVIDENCE`** (true): a screenshot and an observed value after every executed test step. When false, only the failing step is screenshotted.
- **`AGENTS_TRANSIENT_RETRIES`** (3) / **`AGENTS_RETRY_BACKOFF_SECONDS`** (2): HTTP 429/5xx errors and dropped connections are retried with backoff of 2, 4 and 8 s. Timeouts and other 4xx errors are not. Every try is its own `llm_calls` entry, with `transport_try` and `retry_in_s`.
- **`VISION_MODEL_NAME`**: `qwen2.5vl:3b`, pulled by `vision-model/entrypoint.sh`.
- **`AGENTS_LLM_PROVIDER/BASE_URL/MODEL_NAME`**: the text agents. When unset, they use the vision model, so only one extra model is kept in RAM. The chat default `qwen2.5:0.5b-instruct` is too small for rule extraction.
- **`AGENTS_NUM_CTX`** (8192): the Ollama context window. The prompts carry the DOM list, rules and cases, which overflow Ollama's 2048 default.
- **`AGENTS_TEMPERATURE`** (0): makes reruns comparable.
- **Timeouts:** `VISION_REQUEST_TIMEOUT_SECONDS` / `AGENTS_LLM_TIMEOUT_SECONDS` (1800) and `TEST_RUNNER_STEP_TIMEOUT_MS` (5000 per step).
- **`AGENTS_VISION_MAX_WIDTH`** (640): the width of the downscaled screenshot the vision model receives. The full-size capture is still saved for humans.
- **`AGENTS_NUM_PREDICT`** (3072): a cap on generated tokens per call, applied to **Ollama only**. It is never sent to Gemini as `maxOutputTokens`: see Gotchas.
- **`AGENTS_RUN_TIMEOUT_SECONDS`** (7200): a queued or running record that hasn't been updated for this long is reported as `stale`, for example after a backend restart mid-run.

## Gotchas in the Agents pipeline

- **Gemini needs the JSON schema, not just a JSON mime type.** With only `responseMimeType`, `gemini-flash-latest` returned `navigation` as objects where `UiAnalysis` wants strings, and did it again on the repair attempt, so the run failed. The schema is now sent as `generationConfig.responseJsonSchema`. Gemini accepted the full pydantic schema, nested `$defs` included, and the answer validated.
- **Gemini answers were cut short while `maxOutputTokens` was set.** With `num_predict` mapped onto `maxOutputTokens=3072`, first attempts came back as 351-character fragments cut mid-string ("Invalid JSON"); the repair attempt usually got through. The suspected cause is that `gemini-flash-latest` is a thinking model whose thinking tokens count toward that budget. The quota ran out before this could be confirmed. Gemini no longer gets the cap. Agent calls pass `fail_on_truncation=True`, so a length-limited answer (Gemini `finishReason=MAX_TOKENS`, Ollama `done_reason=length`) is logged as "response truncated" instead of a misleading parse error. Chat streaming is unchanged.
- **The Gemini free tier runs out quickly.** A run makes 5 or more calls, and the repairs add more. After a few runs in one session every call returned `429 You exceeded your current quota`. Retries cannot help with a daily quota; the run fails at the first agent step, with the 429 recorded in `llm_calls`.
- **A run interrupted by a backend restart used to look alive.** A record left as `running` blocked the UI's Run button until `AGENTS_RUN_TIMEOUT_SECONDS`. The active run id now lives in `run_store`, and any queued or running record this process is not executing is reported as `stale` immediately.

- **CPU inference speed decides whether a fully local run is practical.** Measured on the dev box, `qwen2.5vl:3b` in Docker processed prompts at about **7 tokens/s** and generated at about **2.3 tokens/s**. The first cold model load took 192 s.
  - The first local run sent a 1280 px full-page screenshot (about 2,000 image tokens) plus indented JSON. Step 2 hit the 600 s `ReadTimeout` before the first token; the run was marked `failed` with the error logged on `step2_ui_analysis`.
  - The fixes: the vision model now receives a 640 px copy (`vision_image`), prompts use compact JSON (`llm_json.prompt_json`), output is capped (`num_predict`), and timeouts are 1800 s.
  - For fast runs, point the text agents at a bigger or remote model with `AGENTS_LLM_PROVIDER` / `AGENTS_LLM_MODEL_NAME`, or run Ollama on a GPU.

- **`LLM_PROVIDER=google` in `.env` used to hijack the agents.** The first version made `vision_provider` fall back to `llm_provider`, so on this dev box the "local vision model" run actually called Gemini. It is now its own setting with an `ollama` default.
- **The myweb rules are stated twice.** They appear in `myweb/site/myweb/app.js` and verbatim in `agents/defaults.py::DEFAULT_REGISTER_REQUIREMENT`. Change both together, or the business agent will "confirm" rules the page doesn't implement.
- **`<img src>` can't carry `X-User-Id`.** Screenshots and the spec are fetched through `apiFetch` as blobs (`fetchAgentArtifact`) and shown with `URL.createObjectURL`.
- **The Playwright pip version must match the image tag.** `test-runner/requirements.txt` has `playwright==1.49.1` and the Dockerfile uses `playwright/python:v1.49.1-noble`. A mismatch fails at launch with "Executable doesn't exist".
- **pytest collects classes whose names start with `Test`.** `TestStep`, `TestCase`, `TestDesign`, `TestRunnerClient` and `TestRunnerError` set `__test__ = False`. The check function was renamed to `design_checks` for the same reason.
- **Validation messages are hidden at capture time.** A `text=` locator for "First name is required." therefore finds no DOM match in step 1. Tests should target `#firstName-error` (css id) instead; `locators_match_dom` flags `text` locators for hidden messages as warnings.

## Verification of the Agents pipeline

- **Run folder and evidence, live:** `live_evidence_check.py` (session scratch) ran inside the backend container against the real test-runner and myweb, using two approved cases.
  - It produced run `b1eb3375…` with `agents/01_test_automation/`, plus `test-cases/TC-REG-00{1,2}/` each holding `test-case.md`, `result.json` and 6 and 3 evidence PNGs.
  - TC-REG-001 passed, observing `text='Account 123 has been created successfully!'`.
  - TC-REG-002, whose expected text was deliberately wrong, failed with `observed text='First name is required.'`.
  - All of these files are served through `/agents/runs/{id}/artifacts/...`, and traversal returns 404.
- **Local run through step 7:** local run `92cc24d2…` got through all 6 earlier steps in about 2 h. Step 7 then failed with `response truncated (done_reason=length)` because it sent every step of every result. Step 7 now sends one compact result per case (its status, and for a failure the failing step with its error and observed value).

- **Backend:** run `cd backend && .venv/Scripts/python -m pytest -q`. Expected: `248 passed`. `ruff check src tests`, `mypy src` and `black --check` are all clean.
- **Real browser against myweb:** run `docker compose run --rm test-runner python -m pytest`. Expected: `8 passed`. This covers required errors, email and DOB format, a future DOB, a 51-character name, the "Account 123" banner, Back resetting the form, fresh context per case, and fail-then-skip with a screenshot.
- **Frontend:** `cd frontend && npm run build` succeeds.
- **End to end (Gemini, before the provider fix):** run `66c1b822…` succeeded in about 50 s.
  - 7 cases were designed and all 7 approved in round 1; all 7 then passed in real Chromium.
  - The repair retry fired once in step 2 and once in step 4, and both attempts are visible in `llm_calls`.
- **End to end, local `qwen2.5vl:3b` (CPU):**
  - The first run timed out in step 2 after 600 s.
  - After the downscaling and compact-JSON fixes, step 2 **succeeded in 12 min** (719 s). Step 3 then failed with `RemoteProtocolError` from Ollama, which is now retried as transient.
  - A full local run was never completed; expect over an hour per run on this CPU.
- **End to end, Gemini (`gemini-flash-latest`), run `047d650c…`:** succeeded in 2 min 17 s.
  - 12 rules and 9 cases; all 9 were approved in round 1, all 9 passed in Playwright, and all 12 rules are verified.
  - Transient 503 and 429 errors on steps 3 and 5 were retried and logged.
  - The `uncovered_rules_match_computed` check flagged the confirmation agent claiming BR-005 was uncovered, which the code-computed coverage contradicts.
- **Manual:**
  1. Run `docker compose up -d --build`.
  2. Open http://localhost:8080/myweb.
  3. Check that `curl localhost:8002/api/tags` lists `qwen2.5vl:3b`.
  4. In the Agents tab, click **Run agents**, then expand any step to see Input / Output / Checks / LLM calls.
