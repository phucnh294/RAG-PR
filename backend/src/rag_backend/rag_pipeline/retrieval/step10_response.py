from __future__ import annotations

import json

from rag_backend.schemas.chat import Citation

# Separates the streamed answer text from the trailing citations payload.
CITATIONS_MARKER = "\x00CITATIONS:"


def build_citations_payload(citations: list[Citation]) -> bytes:
    """Build the final chunk appended after the streamed answer: the citations as JSON."""
    citations_json = json.dumps([citation.model_dump() for citation in citations])
    return f"{CITATIONS_MARKER}{citations_json}".encode()
