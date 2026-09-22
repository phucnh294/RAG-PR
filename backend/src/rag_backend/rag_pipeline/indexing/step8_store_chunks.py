from __future__ import annotations

import uuid

from rag_backend.db import postgres_store
from rag_backend.rag_pipeline.indexing.step6_embedding import EmbeddedChunk
from rag_backend.storage.records import ChunkRecord


async def store_chunks(document_id: str, embedded_chunks: list[EmbeddedChunk]) -> None:
    records = [
        ChunkRecord(
            id=str(uuid.uuid4()),
            document_id=document_id,
            chunk_index=embedded.chunk_with_metadata.chunk.chunk_index,
            content=embedded.chunk_with_metadata.chunk.content,
            embedding=embedded.embedding,
            metadata={
                "word_count": embedded.chunk_with_metadata.metadata.word_count,
                "char_count": embedded.chunk_with_metadata.metadata.char_count,
            },
        )
        for embedded in embedded_chunks
    ]
    await postgres_store.add_chunks(document_id, records)
