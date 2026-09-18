from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step1_get_input import RawQuery
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import normalize_input


def test_normalize_input_collapses_whitespace_and_strips() -> None:
    raw = RawQuery(text="  how   many\n\ndays? ", document_ids=["doc-1"])

    normalized = normalize_input(raw)

    assert normalized.text == "how many days?"
    assert normalized.document_ids == ["doc-1"]
