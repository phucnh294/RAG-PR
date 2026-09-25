from __future__ import annotations

import logging

from rag_backend.config import settings
from rag_backend.exceptions import SemanticCacheError
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.semantic_cache import service as semantic_cache_service
from rag_backend.semantic_cache.models import CacheCandidate

logger = logging.getLogger(__name__)


async def cache_lookup(
    embedded_query: EmbeddedQuery, state: RetrievalState, use_cache: bool = True
) -> CacheCandidate | None:
    """Look the standalone question up in the permission-locked semantic cache.

    Sets state.cache_status to "disabled" (setting off), "bypassed" (this request opted
    out, or it filters to specific documents — a cached answer was built from the whole
    corpus), "hit", "miss" or "error" (cache unreachable, treated as a miss). The
    permission lock itself lives in semantic_cache.service.lookup.
    """
    if not settings.semantic_cache_enabled:
        state.cache_status = "disabled"
        return None
    if not use_cache or embedded_query.document_ids:
        state.cache_status = "bypassed"
        return None
    try:
        hit = await semantic_cache_service.lookup(embedded_query.embedding, state.user)
    except SemanticCacheError as error:
        logger.warning("Cache lookup failed for request %s: %s", state.request_id, error)
        state.cache_status = "error"
        return None
    if hit is None:
        state.cache_status = "miss"
        return None
    state.cache_status = "hit"
    state.cache_similarity = hit.similarity
    state.cache_entry_id = hit.id
    return hit
