from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk


def apply_metadata_filter(
    scored_chunks: list[ScoredChunk], query: EmbeddedQuery
) -> list[ScoredChunk]:
    """Restrict results to query.document_ids when the caller requested a filter.

    No-op (returns the input unchanged) when no filter was requested, which is the
    only case exercised by the current /chat API today.
    """
    if not query.document_ids:
        return scored_chunks
    allowed_ids = set(query.document_ids)
    return [item for item in scored_chunks if item.chunk.document_id in allowed_ids]
