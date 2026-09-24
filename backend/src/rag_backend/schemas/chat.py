from __future__ import annotations

from pydantic import BaseModel

from rag_backend.guardrails.schemas import EvidenceSummary, GuardrailVerdict

__all__ = [
    "ChatRequest",
    "ChatResponsePayload",
    "Citation",
    "EvidenceSummary",
    "GuardrailVerdict",
]


class ChatRequest(BaseModel):
    message: str


class Citation(BaseModel):
    document_id: str
    filename: str
    excerpt: str
    similarity_score: float


class ChatResponsePayload(BaseModel):
    """Trailing payload streamed after the answer text, behind CITATIONS_MARKER."""

    citations: list[Citation]
    guardrails: list[GuardrailVerdict]
    evidence: EvidenceSummary
