from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rag_backend.guardrails.schemas import GuardrailVerdict

Category = Literal["real", "expect", "attack"]


class GoldenEntry(BaseModel):
    """One golden-set query: a labeled example used to measure guardrail behavior."""

    query: str
    category: Category
    # Filename of a seeded document (resolved to a live document_id at eval time),
    # only meaningful for "real" entries — recall/MRR needs a ground-truth target.
    expected_document_filename: str | None = None
    # Optional text the answering chunk must contain — makes the rerank comparison score
    # chunk-level relevance for long, many-chunk documents (see find_relevant_rank).
    expected_excerpt: str | None = None


class QueryEvalResult(BaseModel):
    """Outcome of running one golden-set entry through the real retrieval pipeline."""

    query: str
    category: Category
    expected_document_id: str | None
    blocked: bool
    matched_rank: int | None
    refused: bool | None
    answer_excerpt: str
    guardrails: list[GuardrailVerdict]


class CategoryMetrics(BaseModel):
    """Aggregated metrics for one query category."""

    category: Category
    query_count: int
    recall_at_k: float | None = None
    mrr: float | None = None
    refusal_rate: float | None = None
    block_rate: float | None = None
    false_block_rate: float | None = None


class EvalReport(BaseModel):
    """Full result of one golden-set evaluation run."""

    generated_at: str
    k: int
    categories: list[CategoryMetrics]
    results: list[QueryEvalResult]


class RankingMetrics(BaseModel):
    """Ranking quality of one arm (hybrid order, or hybrid + rerank) over the queries.

    Each query has one relevant target (see find_relevant_rank), so nDCG@k reduces to
    the mean of 1 / log2(rank + 1) over queries whose target made the top k.
    """

    query_count: int
    recall_at_1: float
    recall_at_k: float
    mrr: float
    ndcg_at_k: float


class RerankQueryResult(BaseModel):
    """Where one query's relevant chunk landed before and after reranking."""

    query: str
    expected_document_filename: str
    expected_excerpt: str | None
    # Position in the full candidate pool the reranker saw (None: retrieval never found
    # it, so no reranker could fix it).
    rank_in_pool: int | None
    rank_before: int | None
    rank_after: int | None
    candidate_count: int
    rerank_status: str
    rerank_duration_ms: float | None


class RerankComparisonReport(BaseModel):
    """Offline A/B of step 6: the same candidate pool ranked by hybrid search alone vs
    reordered by the cross-encoder, scored against the golden set."""

    generated_at: str
    model: str
    search_mode: str
    k: int
    candidate_k: int
    baseline: RankingMetrics
    reranked: RankingMetrics
    delta: RankingMetrics
    # Share of queries whose target was anywhere in the candidate pool: the ceiling
    # recall_at_k can reach by reordering alone.
    pool_recall: float
    improved_count: int
    worsened_count: int
    unchanged_count: int
    rerank_failed_count: int
    mean_rerank_ms: float | None
    p95_rerank_ms: float | None
    # Queries not scored: expected document isn't indexed/visible, or the query errored.
    skipped_queries: list[str]
    results: list[RerankQueryResult]
