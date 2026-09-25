from __future__ import annotations

from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import TextChunk
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import (
    ChunkMetadata,
    ChunkWithMetadata,
)
from rag_backend.rag_pipeline.indexing.step6_embedding import EmbeddedChunk
from rag_backend.rag_pipeline.indexing.step8_store_chunks import store_chunks
from rag_backend.storage import dummy_store


async def test_store_chunks_persists_records_retrievable_by_document_id() -> None:
    chunk = TextChunk(
        document_id="doc-1", chunk_index=0, content="hello", char_offset_start=0, char_offset_end=5
    )
    embedded = EmbeddedChunk(
        chunk_with_metadata=ChunkWithMetadata(
            chunk=chunk, metadata=ChunkMetadata(word_count=1, char_count=5)
        ),
        embedding=[0.1, 0.2, 0.3],
    )

    await store_chunks("doc-1", [embedded])

    stored = await dummy_store.get_chunks("doc-1")
    assert len(stored) == 1
    assert stored[0].content == "hello"
    assert stored[0].embedding == [0.1, 0.2, 0.3]
    assert stored[0].metadata == {"word_count": 1, "char_count": 5, "chunk_strategy": "window"}
