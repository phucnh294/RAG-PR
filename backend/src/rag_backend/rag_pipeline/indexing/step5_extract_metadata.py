from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import STRATEGY_WINDOW, TextChunk


@dataclass
class ChunkMetadata:
    word_count: int
    char_count: int
    chunk_strategy: str = STRATEGY_WINDOW
    section_heading: str | None = None
    question_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Stored as rag_chunks.metadata; unset optional fields are left out."""
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class ChunkWithMetadata:
    chunk: TextChunk
    metadata: ChunkMetadata


def extract_metadata(chunks: list[TextChunk]) -> list[ChunkWithMetadata]:
    """Attach derivable metadata to each chunk: word/char counts plus the chunking
    strategy, section heading and question id step3 recorded."""
    return [
        ChunkWithMetadata(
            chunk=chunk,
            metadata=ChunkMetadata(
                word_count=len(chunk.content.split()),
                char_count=len(chunk.content),
                chunk_strategy=chunk.strategy,
                section_heading=chunk.section_heading,
                question_id=chunk.question_id,
            ),
        )
        for chunk in chunks
    ]
