from __future__ import annotations

from pydantic import BaseModel, Field

from rag_backend.guardrails.schemas import EvidenceSummary, GuardrailVerdict

__all__ = [
    "ChatRequest",
    "ChatResponsePayload",
    "Citation",
    "EvidenceSummary",
    "GuardrailVerdict",
    "RetrievalSummary",
]


class ChatRequest(BaseModel):
    message: str
    # Cross-encoder reranking for this request; None -> settings.rerank_enabled_default.
    rerank: bool | None = None
    # The conversation this message continues; None starts a new one (its id comes back
    # in the X-Conversation-Id header and the payload's conversation_id).
    conversation_id: str | None = None
    # Conversation memory for this request; None -> settings.memory_enabled_default /
    # memory_turns_default. memory_turns is clamped to settings.memory_max_turns.
    memory_enabled: bool | None = None
    memory_turns: int | None = Field(default=None, ge=0)


class Citation(BaseModel):
    document_id: str
    filename: str
    excerpt: str
    similarity_score: float
    # Cross-encoder relevance in [0, 1]; None when reranking didn't run for the request.
    rerank_score: float | None = None


class RetrievalSummary(BaseModel):
    """How retrieval ran for one request, so the UI can show whether reranking applied,
    whether the answer came from the semantic cache and what question was searched."""

    search_mode: str
    rerank_enabled: bool
    rerank_status: str
    rerank_duration_ms: float | None = None
    cache_status: str = "disabled"
    cache_similarity: float | None = None
    memory_enabled: bool = False
    history_turns_used: int = 0
    standalone_question: str | None = None


class ChatResponsePayload(BaseModel):
    """Trailing payload streamed after the answer text, behind CITATIONS_MARKER."""

    citations: list[Citation]
    guardrails: list[GuardrailVerdict]
    evidence: EvidenceSummary
    retrieval: RetrievalSummary | None = None
    conversation_id: str | None = None
