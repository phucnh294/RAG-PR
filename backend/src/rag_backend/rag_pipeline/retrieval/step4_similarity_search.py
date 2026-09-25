from __future__ import annotations

from dataclasses import dataclass

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.storage.records import ChunkRecord


@dataclass
class ScoredChunk:
    """One retrieved chunk.

    similarity_score is always the cosine similarity to the question (used by the
    step-7 threshold and the evidence guardrail). The hybrid fields are None in
    vector-only mode; vector_rank/text_rank are 1-based positions in each retriever's
    list, None when that retriever didn't return the chunk.
    """

    chunk: ChunkRecord
    similarity_score: float
    rrf_score: float | None = None
    vector_rank: int | None = None
    text_rank: int | None = None

    @property
    def matched_fulltext(self) -> bool:
        return self.text_rank is not None


async def similarity_search(query: EmbeddedQuery, top_k: int | None = None) -> list[ScoredChunk]:
    """Retrieve the top_k chunks for the question.

    Hybrid mode (default) runs pgvector cosine search and Postgres full-text search,
    each returning up to hybrid_candidate_k candidates, and fuses them with Reciprocal
    Rank Fusion. Vector-only mode ranks by cosine similarity via pgvector's `<=>`.
    """
    limit = top_k if top_k is not None else settings.retrieval_top_k
    if not settings.hybrid_search_enabled:
        results = await postgres_store.search_similar_chunks(query.embedding, limit)
        return [ScoredChunk(chunk=chunk, similarity_score=score) for chunk, score in results]

    candidate_k = max(settings.hybrid_candidate_k, limit)
    vector_hits = await postgres_store.search_similar_chunks(query.embedding, candidate_k)
    text_hits = await postgres_store.search_fulltext_chunks(
        query.text, query.embedding, candidate_k
    )
    return reciprocal_rank_fusion(vector_hits, text_hits, limit, settings.rrf_k)


def reciprocal_rank_fusion(
    vector_hits: list[tuple[ChunkRecord, float]],
    text_hits: list[tuple[ChunkRecord, float]],
    top_k: int,
    rrf_k: int,
) -> list[ScoredChunk]:
    """Fuse two ranked lists: score(chunk) = sum over lists of 1 / (rrf_k + rank).

    Only ranks matter, so cosine similarity and ts_rank never have to be put on a
    common scale. A chunk ranked well by both retrievers beats one ranked first by
    only one. Ties break on cosine similarity so the order is deterministic.
    """
    fused: dict[str, ScoredChunk] = {}
    scores: dict[str, float] = {}

    for rank, (chunk, similarity) in enumerate(vector_hits, start=1):
        fused.setdefault(chunk.id, ScoredChunk(chunk=chunk, similarity_score=similarity))
        fused[chunk.id].vector_rank = rank
        scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (rrf_k + rank)

    for rank, (chunk, similarity) in enumerate(text_hits, start=1):
        fused.setdefault(chunk.id, ScoredChunk(chunk=chunk, similarity_score=similarity))
        fused[chunk.id].text_rank = rank
        scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (rrf_k + rank)

    for chunk_id, item in fused.items():
        item.rrf_score = scores[chunk_id]

    ranked = sorted(
        fused.values(),
        key=lambda item: (scores[item.chunk.id], item.similarity_score),
        reverse=True,
    )
    return ranked[:top_k]
