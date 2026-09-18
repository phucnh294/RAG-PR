from __future__ import annotations

from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import TextChunk
from rag_backend.rag_pipeline.indexing.step4_preprocessing import preprocess_chunks


def test_preprocess_chunks_collapses_whitespace_and_strips() -> None:
    chunk = TextChunk(
        document_id="doc-1",
        chunk_index=0,
        content="  hello   world\n\nfoo  ",
        char_offset_start=0,
        char_offset_end=10,
    )

    cleaned = preprocess_chunks([chunk])

    assert cleaned[0].content == "hello world foo"
    assert cleaned[0].chunk_index == 0
