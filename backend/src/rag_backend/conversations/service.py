from __future__ import annotations

import logging
from typing import Any

from rag_backend.auth.models import CurrentUser
from rag_backend.conversations import repository
from rag_backend.conversations.models import (
    ASSISTANT_ROLE,
    USER_ROLE,
    ConversationRecord,
    MessageRecord,
    Turn,
)
from rag_backend.exceptions import ConversationNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "New chat"
_TITLE_MAX_CHARS = 60


def title_from_question(question: str) -> str:
    """A conversation title from its first question: one line, at most 60 chars."""
    title = " ".join(question.split())
    if len(title) > _TITLE_MAX_CHARS:
        title = title[: _TITLE_MAX_CHARS - 1].rstrip() + "…"
    return title or DEFAULT_TITLE


async def get_owned_conversation(user: CurrentUser, conversation_id: str) -> ConversationRecord:
    """The user's conversation, or ConversationNotFoundError — also when it is someone
    else's, so a caller can't probe which conversation ids exist. Admins get no bypass:
    conversations are private to their owner."""
    conversation = await repository.get_conversation(conversation_id, user.id)
    if conversation is None:
        raise ConversationNotFoundError(f"Conversation {conversation_id} not found")
    return conversation


async def resolve_conversation(
    user: CurrentUser, conversation_id: str | None, question: str
) -> ConversationRecord:
    """The conversation a chat message belongs to: the named one (owned by the user) or,
    when none is named, a new one titled after the question."""
    if conversation_id is not None:
        return await get_owned_conversation(user, conversation_id)
    conversation = await repository.create_conversation(user.id, title_from_question(question))
    logger.info("Conversation created: conversation=%s user=%s", conversation.id, user.username)
    return conversation


async def record_question(conversation_id: str, question: str) -> MessageRecord:
    return await repository.add_message(conversation_id, USER_ROLE, question)


async def record_answer(
    conversation_id: str,
    answer: str,
    standalone_question: str | None,
    request_id: str,
    cache_hit: bool,
    payload: dict[str, Any],
) -> MessageRecord:
    return await repository.add_message(
        conversation_id,
        ASSISTANT_ROLE,
        answer,
        standalone_question=standalone_question,
        request_id=request_id,
        cache_hit=cache_hit,
        payload=payload,
    )


def pair_turns(messages: list[MessageRecord]) -> list[Turn]:
    """Pair each question with the answer that directly follows it, oldest first.

    A question with no answer after it (the question being answered right now, or one
    whose request died mid-stream) is not a turn and is skipped.
    """
    turns: list[Turn] = []
    pending_question: str | None = None
    for message in messages:
        if message.role == USER_ROLE:
            pending_question = message.content
        elif message.role == ASSISTANT_ROLE and pending_question is not None:
            turns.append(Turn(question=pending_question, answer=message.content))
            pending_question = None
    return turns


async def load_history(conversation_id: str, turns: int) -> list[Turn]:
    """The last `turns` answered exchanges of the conversation, oldest first."""
    if turns <= 0:
        return []
    # Two messages per turn, plus the not-yet-answered current question.
    messages = await repository.get_recent_messages(conversation_id, turns * 2 + 1)
    return pair_turns(messages)[-turns:]
