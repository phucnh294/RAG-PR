from __future__ import annotations

from dataclasses import dataclass

from rag_backend.auth.models import CurrentUser
from rag_backend.pipeline_logging import new_request_id
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step1_get_input import get_input
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import normalize_input
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import embed_question
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import (
    ScoredChunk,
    similarity_search,
)
from rag_backend.rag_pipeline.retrieval.step5_metadata_filter import apply_metadata_filter


@dataclass
class RetrievedCandidates:
    """Steps 1-5 of the retrieval pipeline for one query, stopped before reranking."""

    query_text: str
    chunks: list[ScoredChunk]
    state: RetrievalState


async def retrieve_candidates(
    query: str, user: CurrentUser, top_k: int, rerank_enabled: bool = False
) -> RetrievedCandidates:
    """Run the same steps run_retrieval does up to (not including) step 6, without the
    guardrails, the step-7 threshold or the LLM, so an eval can score the raw ranking.
    """
    normalized = normalize_input(get_input(query))
    embedded = await embed_question(normalized)
    state = RetrievalState(request_id=new_request_id(), user=user)
    state.rerank_enabled = rerank_enabled
    scored = await similarity_search(embedded, state, top_k=top_k)
    filtered = apply_metadata_filter(scored, embedded, state)
    return RetrievedCandidates(query_text=normalized.text, chunks=filtered, state=state)


def _squash(text: str) -> str:
    return " ".join(text.lower().split())


def find_relevant_rank(
    chunks: list[ScoredChunk],
    id_to_filename: dict[str, str],
    expected_filename: str,
    expected_excerpt: str | None = None,
) -> int | None:
    """1-indexed position of the first relevant chunk, or None if none is relevant.

    A chunk is relevant when it belongs to a document named expected_filename (by name,
    not id, so a re-uploaded copy of the same file counts too) and, when an
    expected_excerpt is given, its text contains that excerpt (case/whitespace-
    insensitive). The excerpt makes relevance chunk-level: for a long document, ranking
    *some* chunk of it first isn't the same as ranking the chunk with the answer first.
    """
    excerpt = _squash(expected_excerpt) if expected_excerpt else None
    for rank, item in enumerate(chunks, start=1):
        if id_to_filename.get(item.chunk.document_id) != expected_filename:
            continue
        if excerpt is None or excerpt in _squash(item.chunk.content):
            return rank
    return None
