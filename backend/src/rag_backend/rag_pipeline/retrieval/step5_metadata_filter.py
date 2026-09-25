from __future__ import annotations

import logging

from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk

logger = logging.getLogger(__name__)


def apply_metadata_filter(
    scored_chunks: list[ScoredChunk], query: EmbeddedQuery, state: RetrievalState
) -> list[ScoredChunk]:
    """Drop chunks outside the user's clearance, then restrict to query.document_ids
    when the caller requested a filter.

    The clearance check is defence in depth: step4's SQL already searches only the
    user's readable chunks, so a drop here means a permission bug upstream and is logged
    as a WARNING. A chunk whose classification is unknown is dropped too (fail closed).
    """
    permitted = [
        item
        for item in scored_chunks
        if item.chunk.classification is not None
        and item.chunk.classification in state.allowed_classifications
    ]
    dropped = len(scored_chunks) - len(permitted)
    state.permission_dropped_count = dropped
    if dropped:
        logger.warning(
            "Permission filter dropped %d chunk(s) outside role %s clearance %s — "
            "the search should never return these",
            dropped,
            state.user.role,
            sorted(state.allowed_classifications),
        )

    if not query.document_ids:
        return permitted
    allowed_ids = set(query.document_ids)
    return [item for item in permitted if item.chunk.document_id in allowed_ids]
