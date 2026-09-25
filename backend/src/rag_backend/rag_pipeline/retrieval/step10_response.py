from __future__ import annotations

from rag_backend.guardrails.schemas import EvidenceSummary, GuardrailVerdict
from rag_backend.schemas.chat import ChatResponsePayload, Citation

# Separates the streamed answer text from the trailing response payload.
CITATIONS_MARKER = "\x00CITATIONS:"


def build_citations_payload(
    citations: list[Citation],
    guardrails: list[GuardrailVerdict],
    evidence: EvidenceSummary,
) -> bytes:
    """Build the final chunk appended after the streamed answer: citations, guardrail
    verdicts, and the evidence summary, as JSON.
    """
    payload = ChatResponsePayload(citations=citations, guardrails=guardrails, evidence=evidence)
    return f"{CITATIONS_MARKER}{payload.model_dump_json()}".encode()
