from __future__ import annotations

from dataclasses import dataclass

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.schemas.chat import Citation


@dataclass
class CombinedContext:
    citations: list[Citation]
    context_text: str


async def combine_context(scored_chunks: list[ScoredChunk]) -> CombinedContext:
    """Drop chunks below the minimum similarity threshold, then merge the survivors
    into citations plus a single numbered context block for prompt building.
    """
    surviving = [
        item for item in scored_chunks if item.similarity_score >= settings.min_similarity_score
    ]

    citations: list[Citation] = []
    context_lines: list[str] = []
    for index, item in enumerate(surviving, start=1):
        document = await postgres_store.get_document(item.chunk.document_id)
        filename = document.filename if document is not None else "unknown"
        citations.append(
            Citation(
                document_id=item.chunk.document_id,
                filename=filename,
                excerpt=item.chunk.content,
                similarity_score=item.similarity_score,
            )
        )
        context_lines.append(f"[{index}] ({filename}) {item.chunk.content}")

    return CombinedContext(citations=citations, context_text="\n".join(context_lines))
