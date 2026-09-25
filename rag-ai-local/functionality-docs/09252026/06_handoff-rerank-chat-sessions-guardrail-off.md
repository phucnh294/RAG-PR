---
title: Rerank Deployed, Chat Sessions, Guardrail Judge Off, LLM Failure Handling — Committed on feature/cross-encoder-rerank
date: 2026-09-25
type: session-handoff
area: retrieval-rerank
status: superseded
session_id: 1d4109db-3e76-42fd-818f-e1c4b5ff2169
tags: [retrieval, rerank, cross-encoder, eval, docker, frontend, chat-sessions, guardrails, llm, security]
keywords: [feature/cross-encoder-rerank, reranker-model, ms-marco-MiniLM-L6-v2, onnxruntime, RERANK_CANDIDATE_K, RERANKER_THREADS, ChatSessionList, rag.chatSessions, GUARDRAIL_INPUT_ENABLED, GUARDRAIL_OUTPUT_ENABLED, LlmClientError, llm_unavailable_message, x-goog-api-key, _default_settings]
supersedes: 09252026/05_handoff-cross-encoder-rerank.md
related: [09252026/04_cross-encoder-rerank-design.md]
next_action: Rotate the Gemini API key (it was written into 71 local pipeline-log files before the fix), then push feature/cross-encoder-rerank and open a PR against master.
---

## TL;DR
- **What:** everything from this session is committed on `feature/cross-encoder-rerank`:
  - **Cross-encoder rerank** with its own `reranker-model` container, a chat toggle and before/after measurement.
  - **Tabs keep their state** when you switch between them.
  - **Multiple chat sessions.**
  - **Guardrail LLM judge is turned off** in the local `.env`.
  - **LLM failures show up as a readable answer** instead of an empty bubble.
  - **The Gemini API key no longer goes into logs.**
- **Why:** the user asked for reranking plus quality measurement, then for UI fixes. After that they reported "no response". The cause was Gemini returning 503 in the middle of a stream, and the guardrail judge failing closed.
- **Where:**
  - `reranker-model/`, `docker-compose.yml`
  - backend: `reranker_model/`, `rag_pipeline/retrieval/`, `eval/`, `llm_model/client.py`
  - frontend: `pages/ChatPage.tsx`, `chat/sessions.ts`, `components/ChatSessionList.tsx`, `App.tsx`
- **Impact:**
  - Rerank: Recall@1 73.9%→91.3%, MRR 0.841→0.957, nDCG@5 0.881→0.968, at about 1.7 s mean latency (10 candidates).
  - The full Docker stack is up and verified.

## Current Status
- Branch `feature/cross-encoder-rerank`, one commit on top of `dd7f4a6`. **Not pushed, no PR.**
- Backend: 156 passed / 0 failed. `ruff`, `black --check` and `mypy src` are clean.
- Frontend: `npm run build` OK.
- Docker: all six services are healthy and built from this branch. On 2026-09-25 18:31 a live chat for "When must an unresolved P2 incident be escalated?" got the correct answer "45 minutes", with rerank `applied` and both guardrails reporting "disabled".

## COMPLETED
- **Rerank.** Details are in `04_cross-encoder-rerank-design.md` and the superseded `05_…` handoff.
  - `reranker-model` is a `python:3.12-slim` image running ONNX Runtime. `server.py` exposes a TEI-compatible `POST /rerank` on `:8080`, with the model baked in at pinned commit `233902d`.
  - Default `RERANK_CANDIDATE_K` is 10 and `RERANKER_THREADS` is 6.
  - Before/after comparison: `POST /eval/rerank-comparison`, plus the Evals page panel.
- **Tabs keep their state.** `App.tsx` renders all pages and hides the inactive ones instead of unmounting them. Logs and Documents re-fetch when their tab is opened (the `active` prop) without clearing what's shown. A role switch still remounts everything, via the `userId` key.
- **Chat sessions.**
  - `chat/sessions.ts` stores sessions in localStorage under `rag.chatSessions.<userId>`, capped at 30 and saved once streaming finishes.
  - `ChatPage` owns the sessions and the streaming. Tokens are routed by session id, so switching chats mid-answer is safe.
  - `ChatSessionList` provides new, switch and delete; delete is disabled while that session is streaming.
  - `ChatWindow` is now purely a view.
- **Guardrail judge off.** The repo-root `.env` (gitignored, not committed) sets `GUARDRAIL_INPUT_ENABLED=false` and `GUARDRAIL_OUTPUT_ENABLED=false`. Steps 2b and 9b then return "disabled" without calling any LLM. The input-length check and the evidence signal still run, and neither uses an LLM.
- **LLM failure handling.**
  - `LlmClient.stream_chat` wraps every `httpx.HTTPError` in `LlmClientError` with a log-safe reason (status or error type only).
  - `pipeline.py` step 9 catches it and streams `settings.llm_unavailable_message` plus the citations payload.
  - `streaming.ts` throws if a stream ends with neither text nor payload.
- **Key hygiene.** Gemini now gets the key through the `x-goog-api-key` header instead of `?key=`. `LlmClient` also takes a `transport` for tests (`tests/llm_model/test_client.py`).
- **Test isolation.** The autouse `_default_settings` fixture in `tests/conftest.py` resets every setting to its code default, so the local `.env` can't change test results. Before this fix, `.env`'s `GUARDRAIL_*=false` broke 10 tests.

## NOT DONE / STILL OPEN
1. **Rotate the Gemini API key.** It is not in git (a secret scan of the commit found 0 matches), but it is in plain text in **71 files** under `backend/pipeline-logs/retrieval/`. That folder is gitignored. The key got there through the old `?key=` URL inside judge and LLM error messages. The user has not yet chosen between redacting the files in place and deleting them.
2. **The answer model is still Gemini** (`LLM_PROVIDER=google` in `.env`), so questions still leave the machine. A Gemini outage now shows the "unavailable" message instead of an empty bubble. `LLM_PROVIDER=ollama` would use the local `qwen2.5:0.5b-instruct` container; this was offered to the user but not applied.
3. **Chats have no memory.** The backend answers every message on its own, so a follow-up question doesn't see earlier turns. Fixing this means sending the last N turns in `ChatRequest` and in `build_prompt`; this was offered but not built.
4. **Switching role mid-stream loses that exchange.** `ChatPage` unmounts before the persist effect runs (`frontend/src/pages/ChatPage.tsx`, the `useEffect` that calls `saveSessions`).
5. Open items carried over from `05_…`:
   - The distractor documents `03_holiday_pay_policy.md` and `07_manager_planning_distractor.md` are not indexed.
   - The step-7 threshold ignores `rerank_score` (`step7_combine_context.py:39`).
   - When the reranker is missing, each request pays about 4 s of DNS failure.
   - `CLAUDE.md` still says "greenfield" in its Project status paragraph.
6. `reranker-model` is a custom image, not the official TEI one, because Docker Desktop's proxy returns `denied` for ghcr.io. Switching to TEI means changing the Dockerfile and setting the port back to 80 in compose.

## NEXT ACTION
Rotate the Gemini key in Google AI Studio and put the new one in `.env`. Then push the branch and open the PR:
```bash
docker compose up -d backend          # pick up the new key
git push -u origin feature/cross-encoder-rerank
gh pr create --base master            # base is 10+ commits ahead of master (RBAC, hybrid search)
```

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE
- **What the "no response" bug actually was.** The pipeline logs from 2026-09-25 18:04–18:18 show two failure modes:
  - 18:18: `LlmClient` hit Gemini 503 **after** the `200` StreamingResponse had started. The exception cut the stream, so the UI got an empty body with no payload and no error.
  - 18:04, 18:14, 18:17: the judge returned `judge_error`, which fails closed, so each answer was the 31-character refusal "I can't help with that request.".

  Both are fixed: the judge is off, and LLM errors now become a streamed message.
- **The user explicitly does not want messages sent to an LLM for guardrail judging.** Do not turn `GUARDRAIL_*_ENABLED` back on or move the judge to another provider without asking.
- **`docker compose up -d backend` restarts more than the backend.** Without `--no-deps`, after a `.env` change it also recreated postgres, llm-model and embedding-model, because they share `env_file: .env`. The volumes were unaffected.
- **The tests read the repo-root `.env` through pydantic-settings.** That is why `_default_settings` exists. Any new setting is covered automatically, since the fixture iterates `Settings.model_fields`.
- **Windows editing traps:**
  - Python `write_text` produces cp1252 and CRLF.
  - Several files are CRLF: `docker-compose.yml`, `index.css`, `README.md`, `EvalsPage.tsx`, `llm_model/client.py`.
  - `frontend/src/api/streaming.ts` contains a literal NUL byte in `CITATIONS_MARKER`. Use the Edit tool and verify the byte afterwards.
