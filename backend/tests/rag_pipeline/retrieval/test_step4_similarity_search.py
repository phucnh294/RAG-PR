from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import similarity_search
from rag_backend.storage import dummy_store


async def _add_chunk(document_id: str, embedding: list[float]) -> None:
    await dummy_store.add_chunks(
        document_id,
        [
            dummy_store.ChunkRecord(
                id=f"chunk-{document_id}",
                document_id=document_id,
                chunk_index=0,
                content=f"content for {document_id}",
                embedding=embedding,
                metadata={"word_count": 1, "char_count": 1},
            )
        ],
    )


async def test_similarity_search_ranks_by_cosine_similarity_descending() -> None:
    await _add_chunk("doc-exact", embedding=[1.0, 0.0, 0.0])
    await _add_chunk("doc-orthogonal", embedding=[0.0, 1.0, 0.0])
    await _add_chunk("doc-opposite", embedding=[-1.0, 0.0, 0.0])

    query = EmbeddedQuery(text="q", embedding=[1.0, 0.0, 0.0])
    results = await similarity_search(query, top_k=3)

    assert [item.chunk.document_id for item in results] == [
        "doc-exact",
        "doc-orthogonal",
        "doc-opposite",
    ]
    assert results[0].similarity_score == 1.0
    assert results[2].similarity_score == -1.0


async def test_similarity_search_respects_top_k() -> None:
    await _add_chunk("doc-1", embedding=[1.0, 0.0])
    await _add_chunk("doc-2", embedding=[0.9, 0.1])
    await _add_chunk("doc-3", embedding=[0.1, 0.9])

    query = EmbeddedQuery(text="q", embedding=[1.0, 0.0])
    results = await similarity_search(query, top_k=2)

    assert len(results) == 2
