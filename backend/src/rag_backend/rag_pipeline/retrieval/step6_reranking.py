from __future__ import annotations

import logging
import time

from rag_backend.config import settings
from rag_backend.exceptions import RerankerModelError
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.reranker_model import client as reranker_model_client

logger = logging.getLogger(__name__)


async def rerank(
    query_text: str,
    scored_chunks: list[ScoredChunk],
    state: RetrievalState,
    top_k: int | None = None,
) -> list[ScoredChunk]:
    """Reorder the candidates with the cross-encoder, then cut to top_k.

    Disabled: returns the hybrid/vector order cut to top_k — identical to the pipeline
    before reranking existed. Enabled: scores every (question, chunk) pair, records each
    chunk's pre-rerank position, and sorts by the cross-encoder score (ties keep the
    earlier hybrid position). If the reranker fails, logs it, marks the state "failed"
    and falls back to the hybrid order: a reranker outage costs ranking quality, never
    the answer.

    Looks up reranker_model_client.reranker_client on every call so tests can
    monkeypatch the module-level singleton.
    """
    limit = top_k if top_k is not None else settings.retrieval_top_k
    if not state.rerank_enabled:
        state.rerank_status = "disabled"
        return scored_chunks[:limit]

    state.rerank_candidate_count = len(scored_chunks)
    if not scored_chunks:
        state.rerank_status = "skipped"
        return []

    started = time.perf_counter()
    try:
        scores = await reranker_model_client.reranker_client.score(
            query_text, [item.chunk.content for item in scored_chunks]
        )
    except RerankerModelError:
        state.rerank_status = "failed"
        logger.warning(
            "Reranker failed for request %s; keeping the %s order",
            state.request_id,
            state.search_mode,
            exc_info=True,
        )
        return scored_chunks[:limit]
    finally:
        state.rerank_duration_ms = round((time.perf_counter() - started) * 1000, 2)

    for position, (item, score) in enumerate(zip(scored_chunks, scores, strict=True), start=1):
        item.pre_rerank_rank = position
        item.rerank_score = score
    state.rerank_status = "applied"
    # sorted() is stable, so equal scores keep their hybrid order.
    reranked = sorted(scored_chunks, key=lambda item: item.rerank_score or 0.0, reverse=True)
    return reranked[:limit]
