from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.eval.golden_set import load_golden_set
from rag_backend.eval.retrieval_ranking import find_relevant_rank, retrieve_candidates
from rag_backend.eval.schemas import GoldenEntry, RerankComparisonReport, RerankQueryResult
from rag_backend.eval.scoring import metrics_delta, ranking_metrics
from rag_backend.rag_pipeline.retrieval.step6_reranking import rerank
from rag_backend.reranker_model import client as reranker_model_client

logger = logging.getLogger(__name__)


async def run_rerank_comparison(
    user: CurrentUser, entries: list[GoldenEntry] | None = None, k: int | None = None
) -> RerankComparisonReport:
    """Measure what the step-6 cross-encoder adds on top of hybrid search.

    For every "real" golden-set entry: retrieve one candidate pool (steps 1-5, sized
    rerank_candidate_k exactly as a rerank-enabled chat request would), then rank it two
    ways — the hybrid (RRF) order as-is, and the cross-encoder's order — and find the
    relevant chunk's position in each top k. Both arms see the SAME pool, so any
    difference is the reranker alone. Retrieval only: no guardrails, threshold or LLM,
    so a run is fast and repeatable.

    Entries whose expected document isn't visible to `user` are skipped and listed, not
    scored as misses.
    """
    entries = entries if entries is not None else load_golden_set()
    k = k or settings.retrieval_top_k
    candidate_k = max(settings.rerank_candidate_k, k)

    documents = await postgres_store.list_documents(user.id)
    id_to_filename = {document.id: document.filename for document in documents}
    available_filenames = set(id_to_filename.values())

    results: list[RerankQueryResult] = []
    skipped: list[str] = []
    search_mode = "unknown"
    for entry in entries:
        if entry.category != "real" or entry.expected_document_filename is None:
            continue
        if entry.expected_document_filename not in available_filenames:
            skipped.append(entry.query)
            continue
        try:
            result, search_mode = await _compare_entry(
                entry, entry.expected_document_filename, id_to_filename, user, k, candidate_k
            )
        except Exception:
            # Same rationale as run_golden_set: one query's embedding/search failure
            # must not lose every other query's result.
            logger.exception("Skipping rerank comparison for query: %r", entry.query)
            skipped.append(entry.query)
            continue
        results.append(result)

    return _build_report(results, skipped, search_mode, k, candidate_k)


async def _compare_entry(
    entry: GoldenEntry,
    expected_filename: str,
    id_to_filename: dict[str, str],
    user: CurrentUser,
    k: int,
    candidate_k: int,
) -> tuple[RerankQueryResult, str]:
    candidates = await retrieve_candidates(
        entry.query, user, top_k=candidate_k, rerank_enabled=True
    )
    pool = list(candidates.chunks)
    rank_in_pool = find_relevant_rank(
        pool, id_to_filename, expected_filename, entry.expected_excerpt
    )
    rank_before = find_relevant_rank(
        pool[:k], id_to_filename, expected_filename, entry.expected_excerpt
    )
    reranked = await rerank(candidates.query_text, pool, candidates.state, top_k=k)
    rank_after = find_relevant_rank(
        reranked, id_to_filename, expected_filename, entry.expected_excerpt
    )
    result = RerankQueryResult(
        query=entry.query,
        expected_document_filename=expected_filename,
        expected_excerpt=entry.expected_excerpt,
        rank_in_pool=rank_in_pool,
        rank_before=rank_before,
        rank_after=rank_after,
        candidate_count=len(pool),
        rerank_status=candidates.state.rerank_status,
        rerank_duration_ms=candidates.state.rerank_duration_ms,
    )
    return result, candidates.state.search_mode


def _rank_sort_key(rank: int | None) -> float:
    return math.inf if rank is None else float(rank)


def _p95(values: list[float]) -> float | None:
    """Nearest-rank 95th percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _build_report(
    results: list[RerankQueryResult],
    skipped: list[str],
    search_mode: str,
    k: int,
    candidate_k: int,
) -> RerankComparisonReport:
    baseline = ranking_metrics([result.rank_before for result in results], k)
    reranked = ranking_metrics([result.rank_after for result in results], k)
    before_keys = [_rank_sort_key(result.rank_before) for result in results]
    after_keys = [_rank_sort_key(result.rank_after) for result in results]
    durations = [
        result.rerank_duration_ms
        for result in results
        if result.rerank_status == "applied" and result.rerank_duration_ms is not None
    ]
    return RerankComparisonReport(
        generated_at=datetime.now(UTC).isoformat(),
        model=reranker_model_client.reranker_client.model_name,
        search_mode=search_mode,
        k=k,
        candidate_k=candidate_k,
        baseline=baseline,
        reranked=reranked,
        delta=metrics_delta(baseline, reranked),
        pool_recall=(
            sum(1 for result in results if result.rank_in_pool is not None) / len(results)
            if results
            else 0.0
        ),
        improved_count=sum(1 for b, a in zip(before_keys, after_keys, strict=True) if a < b),
        worsened_count=sum(1 for b, a in zip(before_keys, after_keys, strict=True) if a > b),
        unchanged_count=sum(1 for b, a in zip(before_keys, after_keys, strict=True) if a == b),
        rerank_failed_count=sum(1 for result in results if result.rerank_status == "failed"),
        mean_rerank_ms=sum(durations) / len(durations) if durations else None,
        p95_rerank_ms=_p95(durations),
        skipped_queries=skipped,
        results=results,
    )
