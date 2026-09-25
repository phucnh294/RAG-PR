---
title: Permission-Locked Semantic Cache, Server-Side Conversations and Memory — PR from feature/semantic-cache-memory into master
date: 2026-09-25
type: session-handoff
area: retrieval-cache-memory
status: in-progress
session_id: 8e9c6a7b-4d09-40b2-bc10-7e96b1b924be
tags: [retrieval, semantic-cache, conversations, memory, contextualize, authorization, backend, frontend]
keywords: [feature/semantic-cache-memory, feature/cross-encoder-rerank, semantic_cache, conversations, conversation_messages, access_scope, count_accessible_documents, CACHE_MIN_SIMILARITY, MEMORY_TURNS_DEFAULT, CONTEXTUALIZE_ENABLED, X-Conversation-Id, step2c_contextualize, step3b_cache_lookup, step9c_cache_store, use_cache, DELETE /cache]
supersedes: 09252026/06_handoff-rerank-chat-sessions-guardrail-off.md
related: [09252026/07_semantic-cache-conversation-memory-design.md, 09252026/02_rbac-authorization-design.md]
next_action: Get the feature/semantic-cache-memory PR against master reviewed and merged, then decide whether step 2c may keep sending conversation text to Gemini (open item 2).
---

## TL;DR
- **What:** built on the new branch `feature/semantic-cache-memory`, branched from `5cdb118` (the rerank commit, already merged into `master` as PR #15):
  - server-side conversations (`conversation_id` + `user_id`);
  - conversation memory (`memory_enabled` / `memory_turns`);
  - a contextualise step (step 2c) that rewrites follow-ups into standalone questions before embedding and before the cache lookup;
  - a pgvector semantic cache locked by permission: exact access-scope match plus a live check that every cited document is still readable.
- **Why:** the user asked for a semantic cache that never returns an answer to someone without permission, for conversations with ids, for contextualisation before embedding and the cache, and for memory settings. "Chats have no memory" was also open item 3 of handoff 06.
- **Where:**
  - backend: `conversations/`, `semantic_cache/`, `db/chat_schema.py`, retrieval steps `2c`/`3b`/`9c`, `routes_conversations.py`, `routes_cache.py`, and hooks in `routes_upload.py` and `indexing/pipeline.py`;
  - frontend: `ChatPage`, `chat/sessions.ts`, `ChatWindow`, `MessageBubble`;
  - docs: `.env.example`, `README.md`, design doc `07_…`.
- **Impact:**
  - 188/188 backend tests pass; ruff, black and mypy are clean; the frontend builds.
  - On the live stack, a repeated question dropped from 15.6 s to 1.9 s (cache hit).
  - Cross-role requests miss. The `user` role correctly got a *different* answer ("18 days" vs "20 days") instead of the staff one.

## Current Status
- **Code:** complete, verified, committed on `feature/semantic-cache-memory` and opened as a PR against `master`. The PR contains only this commit, because `5cdb118` is already in `origin/master` through PR #15.
- **Tests:** `backend/.venv/Scripts/python -m pytest -q` → **188 passed** (156 old + 32 new), in 22.6 s.
- **Live Docker stack:** `backend` and `frontend` were rebuilt from this working tree and are running. The DB now has the `conversations`, `conversation_messages` and `semantic_cache` tables (created at startup).

## COMPLETED
- **Tables** (`backend/src/rag_backend/db/chat_schema.py`, `ensure_chat_schema()` called from `main.py` lifespan after the authz schema): `conversations`, `conversation_messages` (with `payload jsonb` for citations), and `semantic_cache` (`vector(768)` HNSW, `access_scope text[]`, `cited_document_ids uuid[]`, `expires_at`).
- **Pipeline** (`rag_pipeline/retrieval/pipeline.py`):
  - new `run_retrieval` parameters `conversation_id`, `memory_enabled`, `memory_turns` and `use_cache`;
  - new steps `2c_contextualize`, `3b_cache_lookup` and `9c_cache_store`;
  - `_finish()` saves the assistant message before yielding the payload, on every exit path (blocked input, cache hit, LLM failure, normal);
  - the log record gains `conversation_id`, `history`, `standalone_question` and `cache`.
- **API:**
  - `POST /chat` accepts `conversation_id`, `memory_enabled` and `memory_turns`, and returns `X-Conversation-Id` (CORS-exposed);
  - `GET|POST /conversations`, `GET|DELETE /conversations/{id}`; a foreign id is a 404, with no admin bypass;
  - admin-only `DELETE /cache`.
- **Invalidation:**
  - `run_indexing` success → `invalidate_classification`;
  - `DELETE /documents/{id}` → `invalidate_document`;
  - evals pass `use_cache=False` (`eval/runner.py`).
- **Tests:**
  - new: `test_step3b_cache_lookup.py` (11), `test_step2c_contextualize.py` (5), `test_routes_conversations.py` (14), `tests/conversations/test_service.py` (2), plus 1 in `test_step8_build_prompt.py`;
  - `dummy_store.py` has in-memory conversations and cache, and `conftest.py` patches them;
  - one existing test, `test_chat_rerank_flag_reorders_...`, now disables the cache.
- **SQL verified against real pgvector:** every new statement ran against `rag-postgres-1` inside a rolled-back transaction.
- **Frontend:**
  - conversations are loaded from the server, and messages are fetched lazily;
  - a draft session gets its id from the response header;
  - Conversation memory checkbox plus a "last N turns" input;
  - cache and memory notes in bubbles;
  - the old localStorage sessions are ignored.

## NOT DONE / STILL OPEN
1. **The PR is open but not merged.** Local `master` is behind `origin/master` (it lacks merges #14 and #15); run `git pull` on master before branching again. Handoff 06 wrongly said the rerank branch was unpushed; it had been merged as PR #15.
2. **Contextualise and memory send conversation text to Gemini.** `.env` has `LLM_PROVIDER=google` (`GOOGLE_MODEL_NAME=gemini-flash-lite-latest`), so the step-2c rewrite prompt, which contains prior Q&A, and the history turns in step 8 leave the machine. The user only ruled out LLM *guardrail judging* (handoff 06), but they may want to know this. `CONTEXTUALIZE_ENABLED=false` or `LLM_PROVIDER=ollama` keeps rewrites local or off.
3. **A follow-up answered "I don't know" on the live stack.** "Can unused days be carried over to next year?" was correctly rewritten, but the corpus has no carry-over text. That is a data gap, not a bug. It was not cached, because the evidence rule kept it out.
4. **Rewrite quality is unmeasured.** There is no eval for step 2c. A golden set of (history, follow-up, expected standalone question) would be the next quality step.
5. **The rerank flag is not part of the cache key** (a deliberate decision, see design doc 07). A hit reports `rerank_status: disabled` next to `cache_status: hit`. If the user wants rerank on/off to cache separately, add it to the key in `semantic_cache/repository.py:find_cache_candidates` and `NewCacheEntry`.
6. **The chat-session list does not refresh server titles** after a draft's first answer. It shows the client-side title, which matches the backend's `title_from_question`, until the next reload.
7. **Carried over from handoff 06, unchanged by this session:**
   - rotate the Gemini key that was leaked into old pipeline logs;
   - the step-7 threshold ignores `rerank_score` (`step7_combine_context.py:39`);
   - about 4 s of DNS delay when the reranker is missing;
   - `CLAUDE.md` still says "greenfield";
   - the reranker uses a custom image instead of TEI.

## NEXT ACTION
Review and merge the PR, then sync local master:
```bash
gh pr view --web                                   # from feature/semantic-cache-memory
gh pr merge --merge                                # once reviewed
git -C d:/AI/CLAUDE/RAG checkout master && git -C d:/AI/CLAUDE/RAG pull
```

## CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE
- **User decisions** (AskUserQuestion, this session):
  - **Lock** = exact scope match **plus** a live cited-document check. Rejected: the "doc check only" variant, because a higher-clearance user would get answers built from a narrower corpus.
  - **Contextualise** = rewrite to a standalone question, used for both the cache key and the embedding. Rejected: an extra LLM pass that adapts cached answers to the conversation.
  - **Frontend** fully moved to server conversations.
  - **Memory config** = env defaults plus a per-request override, the same pattern as rerank.
- **Ground truth for the live check** (2026-09-25 ~21:06, pipeline logs up to `20260925T210623426302_…json`), all for "How many days of paid annual leave do employees get?":

  | Role | Result |
  |---|---|
  | staff | miss in 15.6 s, then hit (sim 1.0) in 1.9 s |
  | manager | miss |
  | user | miss, answered "18 days" from `user.md` only |

  The user's different answer proves that per-scope partitioning matters on this corpus.
- **Plan deviation:** the plan listed an invalidation hook for "classification edit (`update_document_metadata`)". None was added, because `update_document_metadata` never changes classification.
- **The upload invalidation runs when indexing finishes, not at upload time.** Invalidating at upload would let entries created during background indexing survive without the new document.
- **Test trap:** the semantic cache is ON in tests by default. Any test asking the same question twice gets a hit on the second request. Every new repository function must also be added to `_CONVERSATION_REPOSITORY_FUNCTIONS` / `_CACHE_REPOSITORY_FUNCTIONS` in `tests/conftest.py`, or it hits the real pool.
- **Shell trap:** a bash heredoc containing JSX/TS template literals failed with "unexpected EOF". Write patch scripts to the scratchpad and run them from there.
- **Line endings:** the working copy is CRLF (`autocrlf`); files written by the Write tool are LF, and git normalizes them. `git diff --stat` showed no whole-file rewrites. The NUL byte in `frontend/src/api/streaming.ts` `CITATIONS_MARKER` was verified as intact (1 byte).
