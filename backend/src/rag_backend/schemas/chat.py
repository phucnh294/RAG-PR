from __future__ import annotations

from pydantic import BaseModel

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


class Citation(BaseModel):
    document_id: str
    filename: str
    excerpt: str
    similarity_score: float
    # Cross-encoder relevance in [0, 1]; None when reranking didn't run for the request.
    rerank_score: float | None = None


class RetrievalSummary(BaseModel):
    """How retrieval ran for one request, so the UI can show whether reranking applied."""

    search_mode: str
    rerank_enabled: bool
    rerank_status: str
    rerank_duration_ms: float | None = None


class ChatResponsePayload(BaseModel):
    """Trailing payload streamed after the answer text, behind CITATIONS_MARKER."""

    citations: list[Citation]
    guardrails: list[GuardrailVerdict]
    evidence: EvidenceSummary
    retrieval: RetrievalSummary | None = None
