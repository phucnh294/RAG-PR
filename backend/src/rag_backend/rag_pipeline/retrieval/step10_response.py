from __future__ import annotations

from rag_backend.guardrails.schemas import EvidenceSummary, GuardrailVerdict
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.schemas.chat import ChatResponsePayload, Citation, RetrievalSummary

# Separates the streamed answer text from the trailing response payload.
CITATIONS_MARKER = "\x00CITATIONS:"


def build_citations_payload(
    citations: list[Citation],
    guardrails: list[GuardrailVerdict],
    evidence: EvidenceSummary,
    state: RetrievalState | None = None,
) -> bytes:
    """Build the final chunk appended after the streamed answer: citations, guardrail
    verdicts, the evidence summary and, when state is given, how retrieval ran (search
    mode and rerank outcome), as JSON.
    """
    retrieval = (
        RetrievalSummary(
            search_mode=state.search_mode,
            rerank_enabled=state.rerank_enabled,
            rerank_status=state.rerank_status,
            rerank_duration_ms=state.rerank_duration_ms,
        )
        if state is not None
        else None
    )
    payload = ChatResponsePayload(
        citations=citations, guardrails=guardrails, evidence=evidence, retrieval=retrieval
    )
    return f"{CITATIONS_MARKER}{payload.model_dump_json()}".encode()
