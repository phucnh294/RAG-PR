from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from rag_backend.auth.models import CurrentUser
from rag_backend.eval.rerank_comparison import run_rerank_comparison
from rag_backend.eval.retrieval_ranking import find_relevant_rank
from rag_backend.eval.schemas import GoldenEntry
from rag_backend.eval.scoring import ndcg_at_k, ranking_metrics
from rag_backend.exceptions import RerankerModelError
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.reranker_model import client as reranker_model_client
from rag_backend.storage.records import ChunkRecord

_LEAVE_QUERY = GoldenEntry(
    query="How many days of paid annual leave do employees get?",
    category="real",
    expected_document_filename="employee_handbook.md",
)


class _InvertingReranker:
    """Scores candidates in reverse of the order they arrive in: whatever hybrid ranked
    first, the "cross-encoder" ranks last."""

    model_name = "inverting"

    async def score(self, query: str, texts: list[str]) -> list[float]:
        return [float(position) for position in range(len(texts))]


class _FailingReranker:
    model_name = "failing"

    async def score(self, query: str, texts: list[str]) -> list[float]:
        raise RerankerModelError("unreachable")


def test_ndcg_at_k_rewards_higher_ranks_and_ignores_ranks_past_k() -> None:
    assert ndcg_at_k(1, 5) == 1.0
    assert ndcg_at_k(3, 5) == pytest.approx(1 / math.log2(4))
    assert ndcg_at_k(6, 5) == 0.0
    assert ndcg_at_k(None, 5) == 0.0


def test_ranking_metrics_averages_over_all_queries_including_misses() -> None:
    metrics = ranking_metrics([1, 2, None, None], k=5)

    assert metrics.query_count == 4
    assert metrics.recall_at_1 == 0.25
    assert metrics.recall_at_k == 0.5
    assert metrics.mrr == pytest.approx((1 + 0.5) / 4)
    assert metrics.ndcg_at_k == pytest.approx((1 + 1 / math.log2(3)) / 4)


def test_find_relevant_rank_with_excerpt_requires_the_answering_chunk() -> None:
    def scored(chunk_index: int, content: str) -> ScoredChunk:
        chunk = ChunkRecord(
            id=f"c{chunk_index}",
            document_id="doc-1",
            chunk_index=chunk_index,
            content=content,
            embedding=[1.0],
            metadata={},
        )
        return ScoredChunk(chunk=chunk, similarity_score=0.9)

    chunks = [scored(0, "Company overview"), scored(1, "Report lost laptops within ONE  hour")]
    filenames = {"doc-1": "policy.md"}

    assert find_relevant_rank(chunks, filenames, "policy.md") == 1
    assert find_relevant_rank(chunks, filenames, "policy.md", "within one hour") == 2
    assert find_relevant_rank(chunks, filenames, "other.md") is None


async def test_rerank_comparison_scores_both_arms_on_the_same_pool(
    auth_users: dict[str, CurrentUser], seeded_corpus: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reranker_model_client, "reranker_client", _InvertingReranker())

    report = await run_rerank_comparison(auth_users["admin"], entries=[_LEAVE_QUERY], k=1)

    result = report.results[0]
    assert result.rank_before == 1
    assert result.rank_after is None
    assert result.rank_in_pool == 1
    assert result.candidate_count == 3
    assert report.baseline.recall_at_1 == 1.0
    assert report.reranked.recall_at_1 == 0.0
    assert report.delta.recall_at_1 == -1.0
    assert report.worsened_count == 1
    assert report.improved_count == 0
    assert report.model == "inverting"
    assert report.mean_rerank_ms is not None


async def test_rerank_comparison_skips_missing_documents_and_non_retrieval_entries(
    auth_users: dict[str, CurrentUser], seeded_corpus: None
) -> None:
    entries = [
        _LEAVE_QUERY,
        GoldenEntry(
            query="How soon must a lost laptop be reported?",
            category="real",
            expected_document_filename="not_indexed.md",
        ),
        GoldenEntry(query="What is the capital of Australia?", category="expect"),
    ]

    report = await run_rerank_comparison(auth_users["admin"], entries=entries)

    assert [result.query for result in report.results] == [_LEAVE_QUERY.query]
    assert report.skipped_queries == ["How soon must a lost laptop be reported?"]


async def test_rerank_comparison_counts_reranker_failures_as_unchanged(
    auth_users: dict[str, CurrentUser], seeded_corpus: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reranker_model_client, "reranker_client", _FailingReranker())

    report = await run_rerank_comparison(auth_users["admin"], entries=[_LEAVE_QUERY])

    assert report.rerank_failed_count == 1
    assert report.unchanged_count == 1
    assert report.delta.mrr == 0.0
    assert report.mean_rerank_ms is None


def test_rerank_comparison_endpoint_is_admin_only(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    assert client.post("/eval/rerank-comparison", headers=role_headers["user"]).status_code == 403

    response = client.post("/eval/rerank-comparison")

    assert response.status_code == 200
    body = response.json()
    assert {"baseline", "reranked", "delta", "results", "skipped_queries"} <= body.keys()
