from __future__ import annotations

from rag_backend.config import settings
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.rag_pipeline.retrieval.step7_combine_context import combine_context
from rag_backend.storage import dummy_store


def _scored_chunk(
    document_id: str, content: str, score: float, text_rank: int | None = None
) -> ScoredChunk:
    chunk = dummy_store.ChunkRecord(
        id=f"chunk-{document_id}",
        document_id=document_id,
        chunk_index=0,
        content=content,
        embedding=[1.0],
        metadata={"word_count": len(content.split()), "char_count": len(content)},
    )
    return ScoredChunk(chunk=chunk, similarity_score=score, text_rank=text_rank)


async def test_combine_context_keeps_fulltext_match_below_threshold(
    admin_state: RetrievalState,
) -> None:
    doc = await dummy_store.add_document(
        filename="errors.md", content_hash="h1", mime_type="text/markdown", size_bytes=10
    )
    below_threshold_score = settings.min_similarity_score - 0.2
    chunks = [
        _scored_chunk(doc.id, "ERR6002 means timeout", below_threshold_score, text_rank=1),
        _scored_chunk(doc.id, "vector-only noise", below_threshold_score),
    ]

    result = await combine_context(chunks, admin_state)

    assert [citation.excerpt for citation in result.citations] == ["ERR6002 means timeout"]
    assert result.evidence.level == "low"


async def test_combine_context_drops_chunks_below_threshold_and_formats_survivors(
    admin_state: RetrievalState,
) -> None:
    doc = await dummy_store.add_document(
        filename="handbook.md", content_hash="h1", mime_type="text/markdown", size_bytes=10
    )
    below_threshold_score = settings.min_similarity_score - 0.01
    above_threshold_score = settings.min_similarity_score + 0.01

    chunks = [
        _scored_chunk(doc.id, "kept content", above_threshold_score),
        _scored_chunk(doc.id, "dropped content", below_threshold_score),
    ]

    result = await combine_context(chunks, admin_state)

    assert len(result.citations) == 1
    assert result.citations[0].excerpt == "kept content"
    assert result.citations[0].filename == "handbook.md"
    assert "[1] (handbook.md) kept content" in result.context_text


async def test_combine_context_returns_empty_when_nothing_survives(
    admin_state: RetrievalState,
) -> None:
    chunks = [_scored_chunk("doc-1", "text", settings.min_similarity_score - 0.5)]

    result = await combine_context(chunks, admin_state)

    assert result.citations == []
    assert result.context_text == ""
    assert result.evidence.level == "none"
    assert result.evidence.top_score is None
    assert result.evidence.surviving_chunk_count == 0


async def test_combine_context_evidence_level_high_for_strong_scores(
    admin_state: RetrievalState,
) -> None:
    doc = await dummy_store.add_document(
        filename="handbook.md", content_hash="h1", mime_type="text/markdown", size_bytes=10
    )
    chunks = [_scored_chunk(doc.id, "kept content", settings.guardrail_evidence_high_threshold)]

    result = await combine_context(chunks, admin_state)

    assert result.evidence.level == "high"
    assert result.evidence.surviving_chunk_count == 1


async def test_combine_context_evidence_level_low_just_above_min_similarity(
    admin_state: RetrievalState,
) -> None:
    doc = await dummy_store.add_document(
        filename="handbook.md", content_hash="h1", mime_type="text/markdown", size_bytes=10
    )
    chunks = [_scored_chunk(doc.id, "kept content", settings.min_similarity_score + 0.001)]

    result = await combine_context(chunks, admin_state)

    assert result.evidence.level == "low"
