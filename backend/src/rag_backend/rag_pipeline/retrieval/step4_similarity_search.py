from __future__ import annotations

import math
from dataclasses import dataclass

from rag_backend.config import settings
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.storage import dummy_store


@dataclass
class ScoredChunk:
    chunk: dummy_store.ChunkRecord
    similarity_score: float


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def similarity_search(query: EmbeddedQuery, top_k: int | None = None) -> list[ScoredChunk]:
    """Rank every stored chunk (across all documents) by cosine similarity, descending."""
    limit = top_k if top_k is not None else settings.retrieval_top_k
    scored = [
        ScoredChunk(
            chunk=chunk, similarity_score=_cosine_similarity(query.embedding, chunk.embedding)
        )
        for chunk in dummy_store.all_chunks()
    ]
    scored.sort(key=lambda item: item.similarity_score, reverse=True)
    return scored[:limit]
