"""Postgres-backed conversation store (conversations / conversation_messages tables,
created by db/chat_schema.py).

Every conversation read takes the owner's user_id, so a handler can't fetch someone
else's conversation by guessing its id. The test suite swaps these functions for the
in-memory versions in storage/dummy_store.py (see tests/conftest.py).
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from rag_backend.conversations.models import ConversationRecord, MessageRecord
from rag_backend.db.session import get_pool


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _row_to_conversation(row: asyncpg.Record) -> ConversationRecord:
    return ConversationRecord(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_message(row: asyncpg.Record) -> MessageRecord:
    return MessageRecord(
        id=str(row["id"]),
        conversation_id=str(row["conversation_id"]),
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        standalone_question=row["standalone_question"],
        request_id=row["request_id"],
        cache_hit=row["cache_hit"],
        payload=row["payload"],
    )


async def create_conversation(user_id: str, title: str) -> ConversationRecord:
    row = await get_pool().fetchrow(
        "INSERT INTO conversations (user_id, title) VALUES ($1, $2) RETURNING *",
        uuid.UUID(user_id),
        title,
    )
    assert row is not None
    return _row_to_conversation(row)


async def get_conversation(conversation_id: str, user_id: str) -> ConversationRecord | None:
    """The conversation, or None when it doesn't exist OR isn't the user's."""
    conversation_uuid, user_uuid = _as_uuid(conversation_id), _as_uuid(user_id)
    if conversation_uuid is None or user_uuid is None:
        return None
    row = await get_pool().fetchrow(
        "SELECT * FROM conversations WHERE id = $1 AND user_id = $2",
        conversation_uuid,
        user_uuid,
    )
    return _row_to_conversation(row) if row is not None else None


async def list_conversations(user_id: str) -> list[ConversationRecord]:
    """The user's conversations, most recently active first."""
    user_uuid = _as_uuid(user_id)
    if user_uuid is None:
        return []
    rows = await get_pool().fetch(
        "SELECT * FROM conversations WHERE user_id = $1 ORDER BY updated_at DESC",
        user_uuid,
    )
    return [_row_to_conversation(row) for row in rows]


async def delete_conversation(conversation_id: str, user_id: str) -> bool:
    conversation_uuid, user_uuid = _as_uuid(conversation_id), _as_uuid(user_id)
    if conversation_uuid is None or user_uuid is None:
        return False
    result = await get_pool().execute(
        "DELETE FROM conversations WHERE id = $1 AND user_id = $2",
        conversation_uuid,
        user_uuid,
    )
    return result == "DELETE 1"


async def add_message(
    conversation_id: str,
    role: str,
    content: str,
    standalone_question: str | None = None,
    request_id: str | None = None,
    cache_hit: bool = False,
    payload: dict[str, Any] | None = None,
) -> MessageRecord:
    """Append a message and bump the conversation's updated_at in one transaction."""
    conversation_uuid = uuid.UUID(conversation_id)
    async with get_pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO conversation_messages
                (conversation_id, role, content, standalone_question, request_id,
                 cache_hit, payload)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            conversation_uuid,
            role,
            content,
            standalone_question,
            request_id,
            cache_hit,
            payload,
        )
        await conn.execute(
            "UPDATE conversations SET updated_at = NOW() WHERE id = $1", conversation_uuid
        )
    assert row is not None
    return _row_to_message(row)


async def get_messages(conversation_id: str) -> list[MessageRecord]:
    """Every message of the conversation, oldest first. Callers check ownership first."""
    rows = await get_pool().fetch(
        "SELECT * FROM conversation_messages WHERE conversation_id = $1 ORDER BY created_at",
        uuid.UUID(conversation_id),
    )
    return [_row_to_message(row) for row in rows]


async def get_recent_messages(conversation_id: str, limit: int) -> list[MessageRecord]:
    """The latest `limit` messages, returned oldest first."""
    rows = await get_pool().fetch(
        """
        SELECT * FROM (
            SELECT * FROM conversation_messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        ) recent
        ORDER BY created_at
        """,
        uuid.UUID(conversation_id),
        limit,
    )
    return [_row_to_message(row) for row in rows]
