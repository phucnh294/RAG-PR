"""Idempotent schema for server-side conversations and the permission-locked semantic cache.

Runs at every startup after authz_schema.ensure_authorization_schema() (conversations
reference users), like the other ensure_* steps, because postgres/init/*.sql only runs
on a fresh volume.

semantic_cache rows carry the access scope they were answered under and the documents
they cite; the lookup (semantic_cache/service.py) matches the scope exactly and then
re-checks every cited document through v_user_accessible_documents, so the cache itself
never widens what a user can read.
"""

from __future__ import annotations

import logging

from rag_backend.config import settings
from rag_backend.db.session import get_pool

logger = logging.getLogger(__name__)

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS conversations_user_updated_idx
    ON conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role                VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content             TEXT NOT NULL,
    standalone_question TEXT,
    request_id          TEXT,
    cache_hit           BOOLEAN NOT NULL DEFAULT FALSE,
    payload             JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS conversation_messages_conversation_idx
    ON conversation_messages (conversation_id, created_at);

CREATE TABLE IF NOT EXISTS semantic_cache (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question             TEXT NOT NULL,
    embedding            vector({dimension}) NOT NULL,
    answer               TEXT NOT NULL,
    citations            JSONB NOT NULL,
    evidence             JSONB NOT NULL,
    cited_document_ids   UUID[] NOT NULL,
    access_scope         TEXT[] NOT NULL,
    llm_model_name       TEXT NOT NULL,
    embedding_model_name TEXT NOT NULL,
    created_by           UUID REFERENCES users(id) ON DELETE SET NULL,
    hit_count            INT NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at           TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS semantic_cache_embedding_idx
    ON semantic_cache USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS semantic_cache_scope_idx ON semantic_cache (access_scope);
CREATE INDEX IF NOT EXISTS semantic_cache_documents_idx
    ON semantic_cache USING GIN (cited_document_ids);
"""


async def ensure_chat_schema() -> None:
    """Create the conversation and semantic-cache tables if they don't exist yet."""
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        # str.replace, not str.format: the SQL has no other braces today, but format()
        # would break the moment one is added.
        await conn.execute(_TABLES_SQL.replace("{dimension}", str(settings.embedding_dimension)))
    logger.info("Chat schema ready (conversations, conversation_messages, semantic_cache)")
