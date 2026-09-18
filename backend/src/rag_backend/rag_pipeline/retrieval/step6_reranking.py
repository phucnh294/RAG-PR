from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk


def rerank(scored_chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """Placeholder — skipped for now. Returns the input unchanged.

    Kept as its own step so the pipeline's shape doesn't change once a real
    reranker (e.g. a cross-encoder over the top-k candidates) is added here.
    """
    return scored_chunks
