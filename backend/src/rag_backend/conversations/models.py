from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"


@dataclass(frozen=True)
class ConversationRecord:
    """One row of the conversations table."""

    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageRecord:
    """One row of conversation_messages: a question (role "user") or an answer.

    payload is the assistant answer's trailing response payload (citations, guardrails,
    evidence, retrieval summary), kept so a reopened conversation shows its citations.
    """

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    standalone_question: str | None = None
    request_id: str | None = None
    cache_hit: bool = False
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class Turn:
    """One answered exchange, as sent back to the LLM for conversation memory."""

    question: str
    answer: str
