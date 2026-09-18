from __future__ import annotations

from rag_backend.config import settings
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.rag_pipeline.retrieval.step7_combine_context import combine_context
from rag_backend.storage import dummy_store


def _scored_chunk(document_id: str, content: str, score: float) -> ScoredChunk:
    chunk = dummy_store.ChunkRecord(
        id=f"chunk-{document_id}",
        document_id=document_id,
        chunk_index=0,
        content=content,
        embedding=[1.0],
        metadata={"word_count": len(content.split()), "char_count": len(content)},
    )
    return ScoredChunk(chunk=chunk, similarity_score=score)


def test_combine_context_drops_chunks_below_threshold_and_formats_survivors() -> None:
    doc = dummy_store.add_document(
        filename="handbook.md", content_hash="h1", mime_type="text/markdown", size_bytes=10
    )
    below_threshold_score = settings.min_similarity_score - 0.01
    above_threshold_score = settings.min_similarity_score + 0.01

    chunks = [
        _scored_chunk(doc.id, "kept content", above_threshold_score),
        _scored_chunk(doc.id, "dropped content", below_threshold_score),
    ]

    result = combine_context(chunks)

    assert len(result.citations) == 1
    assert result.citations[0].excerpt == "kept content"
    assert result.citations[0].filename == "handbook.md"
    assert "[1] (handbook.md) kept content" in result.context_text


def test_combine_context_returns_empty_when_nothing_survives() -> None:
    chunks = [_scored_chunk("doc-1", "text", settings.min_similarity_score - 0.5)]

    result = combine_context(chunks)

    assert result.citations == []
    assert result.context_text == ""
