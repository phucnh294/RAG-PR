from __future__ import annotations

import json

from rag_backend.rag_pipeline.retrieval.step10_response import (
    CITATIONS_MARKER,
    build_citations_payload,
)
from rag_backend.schemas.chat import Citation


def test_build_citations_payload_encodes_marker_and_json() -> None:
    citations = [
        Citation(document_id="doc-1", filename="f.md", excerpt="hello", similarity_score=0.9)
    ]

    payload = build_citations_payload(citations)

    text = payload.decode("utf-8")
    assert text.startswith(CITATIONS_MARKER)
    decoded = json.loads(text[len(CITATIONS_MARKER) :])
    assert decoded[0]["filename"] == "f.md"


def test_build_citations_payload_handles_empty_list() -> None:
    payload = build_citations_payload([])

    assert payload.decode("utf-8") == f"{CITATIONS_MARKER}[]"
