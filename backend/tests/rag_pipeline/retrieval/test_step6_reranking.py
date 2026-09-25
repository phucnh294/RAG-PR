from __future__ import annotations

import pytest

from rag_backend.exceptions import RerankerModelError
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.rag_pipeline.retrieval.step6_reranking import rerank
from rag_backend.reranker_model import client as reranker_model_client
from rag_backend.storage.records import ChunkRecord


def _scored(document_id: str, content: str, rrf_score: float) -> ScoredChunk:
    chunk = ChunkRecord(
        id=f"chunk-{document_id}",
        document_id=document_id,
        chunk_index=0,
        content=content,
        embedding=[1.0],
        metadata={},
        classification="internal",
    )
    return ScoredChunk(chunk=chunk, similarity_score=0.8, rrf_score=rrf_score)


def _hybrid_order() -> list[ScoredChunk]:
    """Hybrid ranks the off-topic chunk first; the answer is last."""
    return [
        _scored("doc-offtopic", "cafeteria menu for the week", 0.03),
        _scored("doc-partial", "leave requests are reviewed by managers", 0.02),
        _scored("doc-answer", "employees get 20 days of paid annual leave", 0.01),
    ]


class _FailingReranker:
    model_name = "failing"

    async def score(self, query: str, texts: list[str]) -> list[float]:
        raise RerankerModelError("reranker-model unreachable")


async def test_rerank_disabled_keeps_hybrid_order_cut_to_top_k(
    admin_state: RetrievalState,
) -> None:
    admin_state.rerank_enabled = False

    result = await rerank("how many days of paid annual leave", _hybrid_order(), admin_state, 2)

    assert [item.chunk.document_id for item in result] == ["doc-offtopic", "doc-partial"]
    assert admin_state.rerank_status == "disabled"
    assert all(item.rerank_score is None for item in result)


async def test_rerank_enabled_reorders_by_cross_encoder_score_and_records_prior_rank(
    admin_state: RetrievalState,
) -> None:
    admin_state.rerank_enabled = True

    result = await rerank("how many days of paid annual leave", _hybrid_order(), admin_state, 2)

    assert result[0].chunk.document_id == "doc-answer"
    assert result[0].pre_rerank_rank == 3
    assert result[0].rerank_score is not None
    assert result[0].rerank_score > (result[1].rerank_score or 0.0)
    assert len(result) == 2
    assert admin_state.rerank_status == "applied"
    assert admin_state.rerank_candidate_count == 3
    assert admin_state.rerank_duration_ms is not None


async def test_rerank_falls_back_to_hybrid_order_when_the_reranker_fails(
    admin_state: RetrievalState, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reranker_model_client, "reranker_client", _FailingReranker())
    admin_state.rerank_enabled = True

    result = await rerank("paid annual leave", _hybrid_order(), admin_state, 2)

    assert [item.chunk.document_id for item in result] == ["doc-offtopic", "doc-partial"]
    assert admin_state.rerank_status == "failed"


async def test_rerank_with_no_candidates_is_skipped(admin_state: RetrievalState) -> None:
    admin_state.rerank_enabled = True

    assert await rerank("anything", [], admin_state) == []
    assert admin_state.rerank_status == "skipped"
