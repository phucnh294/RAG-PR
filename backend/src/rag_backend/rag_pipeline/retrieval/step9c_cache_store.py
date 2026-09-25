from __future__ import annotations

import logging

from rag_backend.exceptions import SemanticCacheError
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.rag_pipeline.retrieval.step7_combine_context import CombinedContext
from rag_backend.semantic_cache import service as semantic_cache_service

logger = logging.getLogger(__name__)


def skip_reason(context: CombinedContext, state: RetrievalState) -> str | None:
    """Why this answer must not be cached, or None when it may be.

    Only answers grounded in at least one citation are cached: an "I don't know" would
    otherwise keep being replayed after the answer is uploaded, and an entry with no
    cited documents couldn't be permission-checked.
    """
    if state.cache_status != "miss":
        return f"cache_status={state.cache_status}"
    if not context.citations:
        return "no citations"
    if context.evidence.level == "none":
        return "no evidence"
    return None


async def cache_store(
    embedded_query: EmbeddedQuery,
    answer: str,
    context: CombinedContext,
    state: RetrievalState,
) -> str | None:
    """Cache a delivered answer under the asker's access scope; returns the entry id.

    Called only after the LLM succeeded and the output guardrail passed. A failed write
    is logged and ignored — the user already has their answer.
    """
    if skip_reason(context, state) is not None:
        return None
    try:
        entry_id = await semantic_cache_service.store(
            question=embedded_query.text,
            embedding=embedded_query.embedding,
            answer=answer,
            citations=[citation.model_dump() for citation in context.citations],
            evidence=context.evidence.model_dump(),
            user=state.user,
        )
    except SemanticCacheError as error:
        logger.warning("Cache store failed for request %s: %s", state.request_id, error)
        return None
    state.cache_entry_id = entry_id
    return entry_id
