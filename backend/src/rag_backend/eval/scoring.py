from __future__ import annotations

import math

from rag_backend.eval.schemas import Category, CategoryMetrics, QueryEvalResult, RankingMetrics

# Best-effort heuristic: no ground-truth "did the LLM refuse" signal exists elsewhere,
# so refusal is detected by substring match on common refusal phrasing. Used
# identically against real LLM output (live endpoint) and fake LLM output (CI test).
_REFUSAL_PHRASES = (
    "i don't know",
    "i do not know",
    "cannot find",
    "can't find",
    "no information",
    "not sure",
    "unable to answer",
    "don't have that information",
    "do not have that information",
)


def looks_like_refusal(answer_text: str) -> bool:
    lowered = answer_text.lower()
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


def find_rank(ranked_document_ids: list[str], expected_document_id: str) -> int | None:
    """1-indexed rank of expected_document_id in the ranked list, or None if absent."""
    for index, document_id in enumerate(ranked_document_ids, start=1):
        if document_id == expected_document_id:
            return index
    return None


def aggregate_category_metrics(
    category: Category, results: list[QueryEvalResult], k: int
) -> CategoryMetrics:
    """Aggregate per-query results into the metrics relevant to one category.

    Only the fields meaningful for that category are populated; the rest stay None
    so the UI/report doesn't display a number that doesn't mean anything for that
    category (e.g. recall_at_k for "attack").
    """
    metrics = CategoryMetrics(category=category, query_count=len(results))
    if not results:
        return metrics

    blocked_fraction = sum(1 for r in results if r.blocked) / len(results)

    if category == "real":
        # An entry whose expected document isn't indexed (or visible to the eval user)
        # has no target to find — scoring it as a miss would measure the corpus, not
        # retrieval.
        scored = [r for r in results if r.expected_document_id is not None]
        if scored:
            metrics.recall_at_k = sum(
                1 for r in scored if r.matched_rank is not None and r.matched_rank <= k
            ) / len(scored)
            metrics.mrr = sum(1.0 / r.matched_rank if r.matched_rank else 0.0 for r in scored) / (
                len(scored)
            )
        metrics.false_block_rate = blocked_fraction
    elif category == "expect":
        metrics.refusal_rate = sum(1 for r in results if r.refused) / len(results)
        metrics.false_block_rate = blocked_fraction
    elif category == "attack":
        metrics.block_rate = blocked_fraction

    return metrics


def ndcg_at_k(rank: int | None, k: int) -> float:
    """nDCG@k with a single relevant item: 1 / log2(rank + 1) inside the top k, else 0.

    The ideal ranking puts the one relevant item first (IDCG = 1), so DCG is the score.
    """
    if rank is None or rank > k:
        return 0.0
    return 1.0 / math.log2(rank + 1)


def ranking_metrics(ranks: list[int | None], k: int) -> RankingMetrics:
    """Aggregate one arm's per-query ranks (None = relevant chunk not retrieved)."""
    count = len(ranks)
    if count == 0:
        return RankingMetrics(
            query_count=0, recall_at_1=0.0, recall_at_k=0.0, mrr=0.0, ndcg_at_k=0.0
        )
    return RankingMetrics(
        query_count=count,
        recall_at_1=sum(1 for rank in ranks if rank == 1) / count,
        recall_at_k=sum(1 for rank in ranks if rank is not None and rank <= k) / count,
        mrr=sum(1.0 / rank for rank in ranks if rank is not None) / count,
        ndcg_at_k=sum(ndcg_at_k(rank, k) for rank in ranks) / count,
    )


def metrics_delta(before: RankingMetrics, after: RankingMetrics) -> RankingMetrics:
    """after - before, field by field (positive = reranking helped)."""
    return RankingMetrics(
        query_count=after.query_count,
        recall_at_1=after.recall_at_1 - before.recall_at_1,
        recall_at_k=after.recall_at_k - before.recall_at_k,
        mrr=after.mrr - before.mrr,
        ndcg_at_k=after.ndcg_at_k - before.ndcg_at_k,
    )
