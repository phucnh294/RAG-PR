from __future__ import annotations

from rag_backend.config import settings
from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import TextChunk
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import (
    ChunkMetadata,
    ChunkWithMetadata,
)
from rag_backend.rag_pipeline.indexing.step6_embedding import embed_chunks


def _chunk_with_metadata(content: str) -> ChunkWithMetadata:
    chunk = TextChunk(
        document_id="doc-1",
        chunk_index=0,
        content=content,
        char_offset_start=0,
        char_offset_end=len(content),
    )
    return ChunkWithMetadata(
        chunk=chunk, metadata=ChunkMetadata(word_count=1, char_count=len(content))
    )


def test_embed_chunks_produces_vectors_of_configured_dimension() -> None:
    embedded = embed_chunks([_chunk_with_metadata("hello")])

    assert len(embedded[0].embedding) == settings.embedding_dimension
    assert all(-1.0 <= value <= 1.0 for value in embedded[0].embedding)


def test_embed_chunks_is_deterministic_for_same_text() -> None:
    first = embed_chunks([_chunk_with_metadata("hello")])
    second = embed_chunks([_chunk_with_metadata("hello")])

    assert first[0].embedding == second[0].embedding


def test_embed_chunks_differs_for_different_text() -> None:
    first = embed_chunks([_chunk_with_metadata("hello")])
    second = embed_chunks([_chunk_with_metadata("goodbye")])

    assert first[0].embedding != second[0].embedding
