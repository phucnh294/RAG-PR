from __future__ import annotations

import pytest

from rag_backend.config import settings
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import (
    reciprocal_rank_fusion,
    similarity_search,
)
from rag_backend.storage import dummy_store
from rag_backend.storage.records import ChunkRecord
from tests.rag_pipeline.retrieval.conftest import RegisterDocument


@pytest.fixture(autouse=True)
def _documents_exist(register_document: RegisterDocument, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every chunk added below belongs to a document the admin can read."""
    original = dummy_store.add_chunks

    async def _add_chunks_with_document(document_id: str, chunks: list[ChunkRecord]) -> None:
        register_document(document_id)
        await original(document_id, chunks)

    monkeypatch.setattr(dummy_store, "add_chunks", _add_chunks_with_document)


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


async def test_similarity_search_ranks_by_cosine_similarity_descending(
    admin_state: RetrievalState,
) -> None:
    await _add_chunk("doc-exact", embedding=[1.0, 0.0, 0.0])
    await _add_chunk("doc-orthogonal", embedding=[0.0, 1.0, 0.0])
    await _add_chunk("doc-opposite", embedding=[-1.0, 0.0, 0.0])

    query = EmbeddedQuery(text="q", embedding=[1.0, 0.0, 0.0])
    results = await similarity_search(query, admin_state, top_k=3)

    assert [item.chunk.document_id for item in results] == [
        "doc-exact",
        "doc-orthogonal",
        "doc-opposite",
    ]
    assert results[0].similarity_score == 1.0
    assert results[2].similarity_score == -1.0


async def test_similarity_search_respects_top_k(admin_state: RetrievalState) -> None:
    await _add_chunk("doc-1", embedding=[1.0, 0.0])
    await _add_chunk("doc-2", embedding=[0.9, 0.1])
    await _add_chunk("doc-3", embedding=[0.1, 0.9])

    query = EmbeddedQuery(text="q", embedding=[1.0, 0.0])
    results = await similarity_search(query, admin_state, top_k=2)

    assert len(results) == 2


async def _add_text_chunk(document_id: str, content: str, embedding: list[float]) -> None:
    await dummy_store.add_chunks(
        document_id,
        [
            dummy_store.ChunkRecord(
                id=f"chunk-{document_id}",
                document_id=document_id,
                chunk_index=0,
                content=content,
                embedding=embedding,
                metadata={"word_count": 1, "char_count": 1},
            )
        ],
    )


async def test_similarity_search_hybrid_surfaces_keyword_only_match(
    admin_state: RetrievalState,
) -> None:
    for index in range(3):
        await _add_text_chunk(f"doc-semantic-{index}", "unrelated prose", [1.0, 0.0])
    await _add_text_chunk("doc-keyword", "raises ERR6002 on timeout", [0.0, 1.0])

    query = EmbeddedQuery(text="what is ERR6002", embedding=[1.0, 0.0])
    results = await similarity_search(query, admin_state, top_k=2)

    assert results[0].chunk.document_id == "doc-keyword"
    assert results[0].text_rank == 1
    assert results[0].vector_rank == 4
    assert results[0].similarity_score == 0.0
    assert results[0].matched_fulltext


async def test_similarity_search_vector_only_when_hybrid_disabled(
    monkeypatch: pytest.MonkeyPatch, admin_state: RetrievalState
) -> None:
    monkeypatch.setattr(settings, "hybrid_search_enabled", False)
    admin_state.search_mode = "vector"
    await _add_text_chunk("doc-semantic", "unrelated prose", [1.0, 0.0])
    await _add_text_chunk("doc-keyword", "raises ERR6002 on timeout", [0.0, 1.0])

    query = EmbeddedQuery(text="what is ERR6002", embedding=[1.0, 0.0])
    results = await similarity_search(query, admin_state, top_k=2)

    assert [item.chunk.document_id for item in results] == ["doc-semantic", "doc-keyword"]
    assert all(item.rrf_score is None for item in results)


def _chunk(chunk_id: str) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id, document_id=chunk_id, chunk_index=0, content="", embedding=[], metadata={}
    )


def test_reciprocal_rank_fusion_prefers_chunk_ranked_by_both_lists() -> None:
    vector_hits = [(_chunk("a"), 0.9), (_chunk("both"), 0.8)]
    text_hits = [(_chunk("b"), 0.1), (_chunk("both"), 0.8)]

    results = reciprocal_rank_fusion(vector_hits, text_hits, top_k=3, rrf_k=60)

    assert [item.chunk.id for item in results] == ["both", "a", "b"]
    assert results[0].rrf_score == pytest.approx(2 / 62)
    assert (results[0].vector_rank, results[0].text_rank) == (2, 2)
    assert results[2].vector_rank is None


def test_reciprocal_rank_fusion_respects_top_k() -> None:
    vector_hits = [(_chunk(str(i)), 0.5) for i in range(5)]

    results = reciprocal_rank_fusion(vector_hits, [], top_k=2, rrf_k=60)

    assert [item.chunk.id for item in results] == ["0", "1"]


async def test_similarity_search_widens_to_rerank_candidate_k_when_rerank_is_enabled(
    admin_state: RetrievalState, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "retrieval_top_k", 2)
    monkeypatch.setattr(settings, "rerank_candidate_k", 4)
    for index in range(6):
        await _add_chunk(f"doc-{index}", embedding=[1.0, float(index), 0.0])
    query = EmbeddedQuery(text="q", embedding=[1.0, 0.0, 0.0])

    admin_state.rerank_enabled = False
    assert len(await similarity_search(query, admin_state)) == 2

    admin_state.rerank_enabled = True
    assert len(await similarity_search(query, admin_state)) == 4
