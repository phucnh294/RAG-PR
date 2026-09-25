from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.eval.golden_set import load_golden_set
from rag_backend.eval.schemas import Category, EvalReport, GoldenEntry, QueryEvalResult
from rag_backend.eval.scoring import aggregate_category_metrics, find_rank, looks_like_refusal
from rag_backend.guardrails.schemas import BLOCKED_VERDICTS, GuardrailVerdict
from rag_backend.rag_pipeline.retrieval.pipeline import run_retrieval
from rag_backend.rag_pipeline.retrieval.step1_get_input import get_input
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import normalize_input
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import embed_question
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import similarity_search
from rag_backend.rag_pipeline.retrieval.step10_response import CITATIONS_MARKER

logger = logging.getLogger(__name__)

_CATEGORIES: tuple[Category, ...] = ("real", "expect", "attack")
_ANSWER_EXCERPT_LENGTH = 200


async def run_golden_set(
    entries: list[GoldenEntry] | None = None, k: int | None = None
) -> EvalReport:
    """Run every golden-set entry through the real retrieval pipeline and score it.

    Runs against whatever guardrail_judge_client/llm_client are currently wired up
    (the real Ollama/Gemini clients in production, or monkeypatched fakes in tests),
    so the same code path measures both "how guardrails perform live" and "does the
    wiring work at all" in CI. An entry whose LLM/judge call fails (timeout, provider
    rate limit, ...) is logged and skipped rather than failing the whole report.
    """
    entries = entries if entries is not None else load_golden_set()
    k = k or settings.retrieval_top_k

    filename_to_id = {doc.filename: doc.id for doc in await postgres_store.list_documents()}

    results: list[QueryEvalResult] = []
    for entry in entries:
        try:
            results.append(await _evaluate_entry(entry, filename_to_id, k))
        except Exception:
            # A single entry's LLM/judge call failing (timeout, provider rate limit,
            # transient network error) shouldn't lose every other entry's results —
            # log it and skip, rather than letting the whole report 500. Broad except
            # is deliberate here, same rationale as the retry-and-continue wrapper in
            # rag_pipeline/retrieval/pipeline.py: the loop must keep going regardless
            # of what specifically went wrong with one entry.
            logger.exception("Skipping golden-set entry due to an error: %r", entry.query)

    categories = [
        aggregate_category_metrics(
            category, [result for result in results if result.category == category], k
        )
        for category in _CATEGORIES
    ]

    return EvalReport(
        generated_at=datetime.now(UTC).isoformat(),
        k=k,
        categories=categories,
        results=results,
    )


async def _evaluate_entry(
    entry: GoldenEntry, filename_to_id: dict[str, str], k: int
) -> QueryEvalResult:
    expected_document_id = (
        filename_to_id.get(entry.expected_document_filename)
        if entry.expected_document_filename
        else None
    )

    chunks = [chunk async for chunk in run_retrieval(entry.query)]
    body = b"".join(chunks).decode("utf-8")
    answer_text, _, payload_json = body.partition(CITATIONS_MARKER)
    payload = json.loads(payload_json)
    guardrails = [GuardrailVerdict.model_validate(item) for item in payload["guardrails"]]
    blocked = any(verdict.verdict in BLOCKED_VERDICTS for verdict in guardrails)

    matched_rank = None
    if entry.category == "real" and expected_document_id is not None:
        matched_rank = await _rank_expected_document(entry.query, expected_document_id, k)

    refused = looks_like_refusal(answer_text) if entry.category == "expect" else None

    return QueryEvalResult(
        query=entry.query,
        category=entry.category,
        expected_document_id=expected_document_id,
        blocked=blocked,
        matched_rank=matched_rank,
        refused=refused,
        answer_excerpt=answer_text[:_ANSWER_EXCERPT_LENGTH],
        guardrails=guardrails,
    )


async def _rank_expected_document(query: str, expected_document_id: str, k: int) -> int | None:
    """Independently rank chunks (bypassing run_retrieval's threshold filtering) to
    get the pre-threshold ranked document list recall/MRR need.
    """
    raw_query = get_input(query)
    normalized = normalize_input(raw_query)
    embedded = await embed_question(normalized)
    scored_chunks = await similarity_search(embedded, top_k=k)
    ranked_document_ids = [item.chunk.document_id for item in scored_chunks]
    return find_rank(ranked_document_ids, expected_document_id)
