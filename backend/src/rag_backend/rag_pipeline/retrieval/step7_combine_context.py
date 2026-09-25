from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.guardrails.schemas import EvidenceSummary
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.schemas.chat import Citation


@dataclass
class CombinedContext:
    citations: list[Citation]
    context_text: str
    evidence: EvidenceSummary


async def combine_context(
    scored_chunks: list[ScoredChunk], state: RetrievalState
) -> CombinedContext:
    """Drop chunks below the minimum similarity threshold, then merge the survivors
    into citations plus a single numbered context block for prompt building.

    Chunks the full-text search matched are kept regardless of cosine score: exact
    identifiers (error codes, config keys, names) are what embeddings rank worst and
    keywords rank best, so filtering them on cosine would undo hybrid search.
    """
    surviving = [
        item
        for item in scored_chunks
        if item.similarity_score >= settings.min_similarity_score or item.matched_fulltext
    ]

    citations: list[Citation] = []
    context_lines: list[str] = []
    for index, item in enumerate(surviving, start=1):
        document = await postgres_store.get_document(item.chunk.document_id, state.user.id)
        filename = document.filename if document is not None else "unknown"
        citations.append(
            Citation(
                document_id=item.chunk.document_id,
                filename=filename,
                excerpt=item.chunk.content,
                similarity_score=item.similarity_score,
            )
        )
        context_lines.append(f"[{index}] ({filename}) {item.chunk.content}")

    evidence = _assess_evidence(surviving)
    return CombinedContext(
        citations=citations, context_text="\n".join(context_lines), evidence=evidence
    )


def _assess_evidence(surviving: list[ScoredChunk]) -> EvidenceSummary:
    """Bucket the surviving (post-threshold) chunks by top/mean cosine score.

    Flag-only Layer 2 guardrail signal: purely descriptive of scores already computed
    in step4, never affects which chunks survive or whether the LLM is called.
    """
    if not surviving:
        return EvidenceSummary(
            level="none",
            top_score=None,
            mean_score=None,
            surviving_chunk_count=0,
            threshold=settings.min_similarity_score,
        )

    scores = [item.similarity_score for item in surviving]
    top_score = max(scores)
    mean_score = sum(scores) / len(scores)

    level: Literal["high", "medium", "low"]
    if top_score >= settings.guardrail_evidence_high_threshold:
        level = "high"
    elif top_score >= settings.guardrail_evidence_medium_threshold:
        level = "medium"
    else:
        level = "low"

    return EvidenceSummary(
        level=level,
        top_score=top_score,
        mean_score=mean_score,
        surviving_chunk_count=len(surviving),
        threshold=settings.min_similarity_score,
    )
