from __future__ import annotations

from rag_backend.eval.schemas import Category, CategoryMetrics, QueryEvalResult

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
        metrics.recall_at_k = sum(
            1 for r in results if r.matched_rank is not None and r.matched_rank <= k
        ) / len(results)
        metrics.mrr = sum(1.0 / r.matched_rank if r.matched_rank else 0.0 for r in results) / len(
            results
        )
        metrics.false_block_rate = blocked_fraction
    elif category == "expect":
        metrics.refusal_rate = sum(1 for r in results if r.refused) / len(results)
        metrics.false_block_rate = blocked_fraction
    elif category == "attack":
        metrics.block_rate = blocked_fraction

    return metrics
