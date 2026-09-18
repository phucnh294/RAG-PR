from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.rag_pipeline.retrieval.step5_metadata_filter import apply_metadata_filter
from rag_backend.storage import dummy_store


def _scored_chunk(document_id: str) -> ScoredChunk:
    chunk = dummy_store.ChunkRecord(
        id=f"chunk-{document_id}",
        document_id=document_id,
        chunk_index=0,
        content="text",
        embedding=[1.0],
        metadata={"word_count": 1, "char_count": 4},
    )
    return ScoredChunk(chunk=chunk, similarity_score=0.9)


def test_apply_metadata_filter_is_noop_without_document_ids() -> None:
    chunks = [_scored_chunk("doc-1"), _scored_chunk("doc-2")]
    query = EmbeddedQuery(text="q", embedding=[1.0], document_ids=None)

    assert apply_metadata_filter(chunks, query) == chunks


def test_apply_metadata_filter_restricts_to_allowed_documents() -> None:
    chunks = [_scored_chunk("doc-1"), _scored_chunk("doc-2")]
    query = EmbeddedQuery(text="q", embedding=[1.0], document_ids=["doc-2"])

    filtered = apply_metadata_filter(chunks, query)

    assert [item.chunk.document_id for item in filtered] == ["doc-2"]
