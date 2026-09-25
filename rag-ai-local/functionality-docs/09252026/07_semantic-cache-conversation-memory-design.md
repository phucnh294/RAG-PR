---
title: Permission-Locked Semantic Cache, Server-Side Conversations and Conversation Memory
date: 2026-09-25
type: functionality
area: retrieval-cache-memory
status: implementation-complete
session_id: 8e9c6a7b-4d09-40b2-bc10-7e96b1b924be
tags: [retrieval, semantic-cache, conversations, memory, contextualize, authorization, pgvector, backend, frontend]
keywords: [semantic_cache, conversations, conversation_messages, access_scope, cited_document_ids, count_accessible_documents, v_user_accessible_documents, CACHE_MIN_SIMILARITY, CACHE_TTL_SECONDS, CACHE_CANDIDATE_K, SEMANTIC_CACHE_ENABLED, MEMORY_ENABLED_DEFAULT, MEMORY_TURNS_DEFAULT, MEMORY_MAX_TURNS, CONTEXTUALIZE_ENABLED, X-Conversation-Id, conversation_id, memory_enabled, memory_turns, cache_status, standalone_question, step2c_contextualize, step3b_cache_lookup, step9c_cache_store, SemanticCacheError, ConversationNotFoundError, use_cache, DELETE /cache]
files:
  - backend/src/rag_backend/db/chat_schema.py
  - backend/src/rag_backend/conversations/models.py
  - backend/src/rag_backend/conversations/repository.py
  - backend/src/rag_backend/conversations/service.py
  - backend/src/rag_backend/semantic_cache/models.py
  - backend/src/rag_backend/semantic_cache/repository.py
  - backend/src/rag_backend/semantic_cache/service.py
  - backend/src/rag_backend/rag_pipeline/retrieval/pipeline.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step2c_contextualize.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step3b_cache_lookup.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step8_build_prompt.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step9c_cache_store.py
  - backend/src/rag_backend/rag_pipeline/retrieval/step10_response.py
  - backend/src/rag_backend/rag_pipeline/indexing/pipeline.py
  - backend/src/rag_backend/api/routes_chat.py
  - backend/src/rag_backend/api/routes_conversations.py
  - backend/src/rag_backend/api/routes_cache.py
  - backend/src/rag_backend/api/routes_upload.py
  - backend/src/rag_backend/db/postgres_store.py
  - backend/src/rag_backend/storage/dummy_store.py
  - frontend/src/pages/ChatPage.tsx
  - frontend/src/chat/sessions.ts
  - frontend/src/components/ChatWindow.tsx
  - frontend/src/components/MessageBubble.tsx
version: 1
last_updated: 2026-09-25
extraction_method: written-during-implementation
related_docs: [09252026/02_rbac-authorization-design.md, 09252026/04_cross-encoder-rerank-design.md, 09252026/06_handoff-rerank-chat-sessions-guardrail-off.md]
---

## TL;DR
- **What:** chats are now server-side conversations. Each conversation has a `conversation_id` and belongs to one `user_id`. Retrieval gained three steps:
  - **2c, contextualise:** rewrites a follow-up into a standalone question.
  - **3b, semantic-cache lookup:** runs on the standalone question's embedding.
  - **9c, cache store:** saves the delivered answer.

  Cached answers are **locked by permission**. A hit requires the same access scope *and* live read access to every cited document. Conversation memory sends the last N turns to the LLM, controlled by `memory_enabled` / `memory_turns`.
- **Why:**
  - chats had no memory (handoff 06 item);
  - chats lived only in browser localStorage;
  - every repeated question paid the full embed → hybrid → rerank → LLM cost.

  In an RBAC system, a naive semantic cache is a data leak: it would replay an answer built from confidential documents to a user who can't read them.
- **Where:**
  - the new `conversations/`, `semantic_cache/` and `db/chat_schema.py` modules;
  - the new retrieval steps `step2c`, `step3b` and `step9c`;
  - the new routes `/conversations` and `DELETE /cache`;
  - invalidation hooks in upload/delete and indexing;
  - the frontend `ChatPage` now loads from the server, and `ChatWindow` has memory toggles.
- **Impact:**
  - A repeated question is answered with no LLM call.
  - A follow-up like "can it be carried over?" is searched as the full question.
  - A cache hit can never widen what a user may read.
  - 188 backend tests pass (156 existing plus 32 new).

## What the semantic cache and conversation memory do in the retrieval pipeline

The retrieval pipeline (`run_retrieval`) now runs in this order:

1. `1 get_input` → `2 normalize` → `2b input guardrail`. The guardrail still checks the message **as typed**.
2. **`2c contextualize`**. If the request belongs to a conversation, memory is on and `memory_turns > 0`, the last N answered turns are loaded. When there is history, one LLM call rewrites the question into a standalone question.
3. `3 embed`, applied to the **standalone** question.
4. **`3b cache lookup`**. On a hit, the cached answer and citations are streamed, the answer is saved into the conversation, and the pipeline returns without calling steps 4–9.
5. `4 hybrid search` → `5 metadata filter` → `6 rerank` (on the standalone question) → `7 combine context`.
6. `8 build prompt`: the system prompt with the context, then the history turns as user/assistant messages, then the standalone question.
7. `9 LLM` → `9b output guardrail` → **`9c cache store`**. Only a delivered, unredacted, grounded answer is stored.
8. `10 response`. The assistant message is saved into the conversation **before** the trailing payload is yielded.

The trailing payload's `retrieval` block now carries `cache_status` (`disabled|bypassed|miss|hit|error`), `cache_similarity`, `memory_enabled`, `history_turns_used` and `standalone_question`. The payload also carries `conversation_id`.

## How the semantic cache permission lock works

A semantic cache entry (`semantic_cache` row) stores:
- the standalone question and its embedding (`vector(768)`, HNSW cosine index);
- the answer, citations and evidence;
- `cited_document_ids`;
- `access_scope`: the asker's allowed classifications, sorted, as `text[]`;
- the answer model (`provider:model`) and the embedding model;
- `expires_at`.

`semantic_cache.service.lookup` serves an entry only if **all** of these hold:

1. **The scope matches exactly.** The SQL filters `access_scope = $2::text[]`. Staff (`[internal, public]`) never match a manager entry (`[confidential, internal, public]`), and managers never match staff entries. Equality rather than a subset check is deliberate; see the decisions section.
2. **The same answer model and embedding model.** Switching `LLM_MODEL_NAME` or the provider makes older entries invisible.
3. **The entry has not expired** (`expires_at > NOW()`).
4. **Cosine similarity ≥ `CACHE_MIN_SIMILARITY`** (0.95).
5. **Live document check.** `postgres_store.count_accessible_documents(cited_ids, user_id)` counts the documents through `v_user_accessible_documents`, and every cited document must be readable **right now**. This catches:
   - a revoked grant, even while the user's in-memory `CurrentUser` still lists the classification;
   - a deactivated user;
   - a deleted document.

Only answers with at least one citation and evidence ≠ `none` are stored. So "I don't know" is never cached, and every entry has documents that can be permission-checked.

## How semantic cache invalidation keeps answers fresh

Semantic cache invalidation is about **freshness**, not permissions. The permission lock never depends on it:

- **A document finishes indexing** (`run_indexing` success, including uploads and seeding): delete every entry whose `access_scope` contains that document's classification. Those answers were built without the new document.
- **A document is deleted** (`DELETE /documents/{id}`): delete every entry whose `cited_document_ids` contains it.
- **An admin flushes the cache:** `DELETE /cache` returns `{"deleted": n}`.
- **TTL:** `CACHE_TTL_SECONDS`, one day by default.
- **Role changes and access-matrix changes need no hook.** The access scope is recomputed from the database on every request, so the user simply lands in a different partition.

Every invalidation call logs and swallows DB errors. Upload, delete and indexing never fail because of the cache.

## How server-side conversations and memory work

- **Tables** (`db/chat_schema.py`, created idempotently at startup after the authorization schema):
  - `conversations(id, user_id → users ON DELETE CASCADE, title, created_at, updated_at)`;
  - `conversation_messages(conversation_id → conversations ON DELETE CASCADE, role user|assistant, content, standalone_question, request_id, cache_hit, payload jsonb, created_at)`. `payload` holds the assistant answer's full response payload, so a reopened chat shows its citations and notes again.
- **`POST /chat`** resolves the conversation **before** streaming starts. An omitted `conversation_id` creates a new conversation, titled from the question. Someone else's id, or an unknown id, returns **404**. The route saves the question, then streams. The new id comes back in the `X-Conversation-Id` header, which CORS exposes.
- **API:** `GET /conversations`, `POST /conversations`, `GET /conversations/{id}` (with messages) and `DELETE /conversations/{id}`. Conversations are private to their owner, **with no admin bypass**. A foreign id is a 404, never a 403, so existence isn't confirmed.
- **Memory:** `conversations.service.load_history` fetches the last `2·turns + 1` messages and pairs each question with the answer right after it. A question without an answer is not a turn. That covers the question being answered right now, which the route already saved, and one whose stream died.
- **Contextualise** (`step2c_contextualize.py`):
  - The prompt contains the history (assistant answers truncated to 500 chars) and the follow-up.
  - The output is cleaned: first line only, a "Standalone question:" echo stripped, quotes stripped.
  - An LLM error or an empty rewrite falls back to the typed question. It never fails the request.
- **Frontend:**
  - `ChatPage` loads `GET /conversations` on mount (the page is remounted per user) and fetches messages lazily when a chat is first opened.
  - "New chat" is a local draft until its first `/chat` response supplies the id.
  - `ChatWindow` has **Conversation memory** and **last N turns** controls, saved in localStorage as `rag.memoryEnabled` / `rag.memoryTurns`.
  - `MessageBubble` shows "Answered from the semantic cache (similarity …)" and "Used N previous turns · searched as: …".

## Key decisions and rejected alternatives

- **Exact scope equality, not "can read all cited docs" alone.**
  - Rejected: serve any entry whose cited documents the asker can read. That gets more hits, but a manager asking a question first answered for staff would get an answer built without the confidential corpus: incomplete, and silently so.
  - Equality partitions the cache by scope. The live document check is layered on top, so a stale scope snapshot can't leak either.
- **The cache key is the standalone question, not the typed text.** "What about it?" means different things in different conversations. Keying on the rewrite makes follow-ups cacheable and stops unrelated follow-ups from colliding.
- **Contextualise happens before embedding and before the cache lookup**, as requested. Cached answers are returned **as-is**. The user explicitly rejected a second LLM pass that rewrites a cached answer to fit the conversation, because it would cost an LLM call on every hit.
- **The input guardrail runs on the typed message, not the rewrite.** The guardrail judges what the user actually sent. A rewrite could launder an injection into a neutral-looking question.
- **The history sent to the LLM uses the original questions; the final user message is the standalone question.** The model sees the conversation as it happened and an unambiguous current question.
- **Evals bypass the cache** (`run_retrieval(..., use_cache=False)`), so a cached answer never masks a retrieval regression. A request with a `document_ids` filter also bypasses it, because cached answers were built from the whole readable corpus.
- **The rerank flag is not part of the cache key.** A cached answer is served whether the request asked for rerank or not, and `rerank_status` then reads `disabled` next to `cache_status: hit`. That's why `test_chat_rerank_flag_reorders_...` now turns the cache off.
- **The user question is saved in the route, the answer in the pipeline.** This way a 404 happens before streaming starts. The answer is saved before the payload is yielded, so the next question's history always includes it.
- **The semantic cache lives in the same Postgres/pgvector instance** rather than Redis. The permission check has to join `v_user_accessible_documents` anyway, and pgvector already gives an ANN index.

## Configuration settings for the semantic cache and memory

| Setting | Default | Runtime effect |
|---|---|---|
| `SEMANTIC_CACHE_ENABLED` | `true` | Off → `cache_status: disabled`; nothing is read or written |
| `CACHE_MIN_SIMILARITY` | `0.95` | Cosine threshold between standalone questions. Lower → more hits **and** more wrong answers to merely similar questions |
| `CACHE_CANDIDATE_K` | `5` | Nearest same-scope entries tried. A candidate failing the live document check falls through to the next |
| `CACHE_TTL_SECONDS` | `86400` | Entry lifetime, set at insert (`expires_at`) |
| `MEMORY_ENABLED_DEFAULT` | `true` | Used when a request omits `memory_enabled` (the UI always sends it) |
| `MEMORY_TURNS_DEFAULT` | `3` | Used when a request omits `memory_turns` |
| `MEMORY_MAX_TURNS` | `10` | A request's `memory_turns` is clamped to this (the pipeline clamps; the schema only enforces ≥ 0) |
| `CONTEXTUALIZE_ENABLED` | `true` | Off → history still reaches the answer LLM, but retrieval and the cache use the typed question |

## Gotchas

- **Contextualise costs one extra LLM call per follow-up.** With the local `qwen2.5:0.5b-instruct`, the rewrite quality is modest. If it rewrites badly, retrieval gets worse for follow-ups; turn it off with `CONTEXTUALIZE_ENABLED=false`. The call goes to the **main answer LLM** (`llm_client.complete_chat`), not to the guardrail judge. Handoff 06 records that the user doesn't want messages sent to an LLM *for guardrail judging*, and that preference is unaffected.
- **A cached answer may have been written with some conversation history in its prompt.** Because the key is the standalone question, the answer is normally self-contained, but it can occasionally reference "as mentioned above". Lower the TTL or clear the cache (`DELETE /cache`) if that shows up.
- **`update_document_metadata` never changes classification**, so it needs no invalidation hook. The plan listed one, but the code path doesn't exist.
- **The upload hook fires when indexing finishes, not when the upload is accepted.** Indexing runs as a background task. Invalidating at upload time would let entries created during indexing survive without the new document.
- **In-memory test fakes:** `tests/conftest.py` must list every new repository function in `_CONVERSATION_REPOSITORY_FUNCTIONS` / `_CACHE_REPOSITORY_FUNCTIONS`, or a test hits `get_pool()` and fails with "pool not initialised".
- **The cache is on by default in tests.** Any test that sends the same question twice now gets a hit the second time. Turn it off with `monkeypatch.setattr(settings, "semantic_cache_enabled", False)` when the test compares retrieval behaviour.
- **Old browser chats are not migrated.** Chats saved under localStorage `rag.chatSessions.<userId>` are ignored now that history lives on the server.

## Verification

- **Backend** (from `backend/`):
  - `.venv/Scripts/python -m pytest -q` → **188 passed**.
    - `test_step3b_cache_lookup.py` covers: same-scope hit; higher- and lower-clearance miss; deleted document; revoked grant with a stale user; below threshold; expired; other model; bypass; disabled; outage → `error`.
    - `test_routes_conversations.py` covers: CRUD and privacy; auto-create plus the header; foreign-id 404; contextualised follow-up plus history in the prompt; memory off; `memory_turns` limit; cache hit with no LLM call; cross-role miss; invalidation on upload and delete; no caching of "don't know"; admin-only `DELETE /cache`.
  - `python -m ruff check .`, `python -m black --check .` and `python -m mypy src` are all clean.
- **Real Postgres/pgvector:**
  - Every new SQL statement (the DDL run twice, all conversation and cache repository functions, `count_accessible_documents`) was executed against the running `rag-postgres-1` inside a transaction and then rolled back.
  - The HNSW index, the `text[]` scope equality, `ANY(uuid[])` and jsonb round-tripping all work.
- **Frontend** (from `frontend/`): `npm run build` passes (`tsc -b` + `vite build`).
- **Live stack check (2026-09-25).** After `docker compose up -d --build backend frontend`, the backend logged "Chat schema ready". Each step below is a `POST /chat` with the question "How many days of paid annual leave do employees get?":

  | Step | Result |
  |---|---|
  | Staff, 1st ask | `cache=miss`, **15.6 s**, answer "20 days" |
  | Staff, 2nd ask | `cache=hit sim=1.0`, **1.9 s**, same answer and citations |
  | Manager | `cache=miss`, a different scope |
  | User | `cache=miss`, **a different answer**: "18 days", cited only from `user.md` |
  | Staff follow-up in the same conversation: "Can unused days be carried over to next year?" | `turns=1`, `standalone_question="Can unused days of paid annual leave be carried over to next year?"` |
  | Manager, `GET /conversations/<staff conversation>` | **404** |

  The user row is the case the permission lock exists for. A scope-blind cache would have replayed the staff answer ("20 days", built partly from internal documents) to the user.
