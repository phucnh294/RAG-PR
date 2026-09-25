from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    standalone_question: str | None = None
    cache_hit: bool = False
    # The assistant answer's response payload (citations, guardrails, evidence, retrieval).
    payload: dict[str, Any] | None = None


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class CacheClearedOut(BaseModel):
    deleted: int
