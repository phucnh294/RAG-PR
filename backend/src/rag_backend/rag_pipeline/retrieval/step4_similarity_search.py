from __future__ import annotations

from dataclasses import dataclass

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.storage.records import ChunkRecord


@dataclass
class ScoredChunk:
    chunk: ChunkRecord
    similarity_score: float


async def similarity_search(query: EmbeddedQuery, top_k: int | None = None) -> list[ScoredChunk]:
    """Rank stored chunks by cosine similarity, descending, via pgvector's `<=>` operator."""
    limit = top_k if top_k is not None else settings.retrieval_top_k
    results = await postgres_store.search_similar_chunks(query.embedding, limit)
    return [ScoredChunk(chunk=chunk, similarity_score=score) for chunk, score in results]
