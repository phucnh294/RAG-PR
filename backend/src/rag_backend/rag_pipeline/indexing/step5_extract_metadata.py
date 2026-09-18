from __future__ import annotations

from dataclasses import dataclass

from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import TextChunk


@dataclass
class ChunkMetadata:
    word_count: int
    char_count: int


@dataclass
class ChunkWithMetadata:
    chunk: TextChunk
    metadata: ChunkMetadata


def extract_metadata(chunks: list[TextChunk]) -> list[ChunkWithMetadata]:
    """Attach lightweight, derivable metadata (word/char counts) to each chunk."""
    return [
        ChunkWithMetadata(
            chunk=chunk,
            metadata=ChunkMetadata(
                word_count=len(chunk.content.split()),
                char_count=len(chunk.content),
            ),
        )
        for chunk in chunks
    ]
