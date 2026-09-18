from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.rag_pipeline.retrieval.step6_reranking import rerank
from rag_backend.storage import dummy_store


def test_rerank_is_a_noop_placeholder() -> None:
    chunk = dummy_store.ChunkRecord(
        id="chunk-1",
        document_id="doc-1",
        chunk_index=0,
        content="text",
        embedding=[1.0],
        metadata={"word_count": 1, "char_count": 4},
    )
    scored = [ScoredChunk(chunk=chunk, similarity_score=0.5)]

    assert rerank(scored) == scored
