from __future__ import annotations

from rag_backend.guardrails.schemas import EvidenceSummary, GuardrailVerdict
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.schemas.chat import ChatResponsePayload, Citation, RetrievalSummary

# Separates the streamed answer text from the trailing response payload.
CITATIONS_MARKER = "\x00CITATIONS:"


def build_response_payload(
    citations: list[Citation],
    guardrails: list[GuardrailVerdict],
    evidence: EvidenceSummary,
    state: RetrievalState | None = None,
) -> ChatResponsePayload:
    """The trailing response payload: citations, guardrail verdicts, the evidence summary
    and, when state is given, how retrieval ran (search mode, rerank and cache outcome,
    memory) plus the conversation it belongs to."""
    retrieval = (
        RetrievalSummary(
            search_mode=state.search_mode,
            rerank_enabled=state.rerank_enabled,
            rerank_status=state.rerank_status,
            rerank_duration_ms=state.rerank_duration_ms,
            cache_status=state.cache_status,
            cache_similarity=state.cache_similarity,
            memory_enabled=state.memory_enabled,
            history_turns_used=state.history_turns_used,
            standalone_question=state.standalone_question,
        )
        if state is not None
        else None
    )
    return ChatResponsePayload(
        citations=citations,
        guardrails=guardrails,
        evidence=evidence,
        retrieval=retrieval,
        conversation_id=state.conversation_id if state is not None else None,
    )


def encode_payload(payload: ChatResponsePayload) -> bytes:
    """The final chunk appended after the streamed answer: marker + payload JSON."""
    return f"{CITATIONS_MARKER}{payload.model_dump_json()}".encode()


def build_citations_payload(
    citations: list[Citation],
    guardrails: list[GuardrailVerdict],
    evidence: EvidenceSummary,
    state: RetrievalState | None = None,
) -> bytes:
    """build_response_payload + encode_payload in one call."""
    return encode_payload(build_response_payload(citations, guardrails, evidence, state))
