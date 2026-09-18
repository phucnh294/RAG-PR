from __future__ import annotations

from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import TextChunk
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import extract_metadata


def test_extract_metadata_computes_word_and_char_counts() -> None:
    chunk = TextChunk(
        document_id="doc-1",
        chunk_index=0,
        content="hello world",
        char_offset_start=0,
        char_offset_end=11,
    )

    result = extract_metadata([chunk])

    assert result[0].metadata.word_count == 2
    assert result[0].metadata.char_count == 11
