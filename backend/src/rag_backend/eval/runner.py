from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.eval.golden_set import load_golden_set
from rag_backend.eval.retrieval_ranking import find_relevant_rank, retrieve_candidates
from rag_backend.eval.schemas import Category, EvalReport, GoldenEntry, QueryEvalResult
from rag_backend.eval.scoring import aggregate_category_metrics, looks_like_refusal
from rag_backend.guardrails.schemas import BLOCKED_VERDICTS, GuardrailVerdict
from rag_backend.rag_pipeline.retrieval.pipeline import run_retrieval
from rag_backend.rag_pipeline.retrieval.step10_response import CITATIONS_MARKER

logger = logging.getLogger(__name__)

_CATEGORIES: tuple[Category, ...] = ("real", "expect", "attack")
_ANSWER_EXCERPT_LENGTH = 200


async def run_golden_set(
    user: CurrentUser, entries: list[GoldenEntry] | None = None, k: int | None = None
) -> EvalReport:
    """Run every golden-set entry through the real retrieval pipeline and score it.

    Runs against whatever guardrail_judge_client/llm_client are currently wired up
    (the real Ollama/Gemini clients in production, or monkeypatched fakes in tests),
    so the same code path measures both "how guardrails perform live" and "does the
    wiring work at all" in CI. An entry whose LLM/judge call fails (timeout, provider
    rate limit, ...) is logged and skipped rather than failing the whole report.

    Runs as `user` (the admin who triggered it), so retrieval sees exactly the documents
    that user may read.
    """
    entries = entries if entries is not None else load_golden_set()
    k = k or settings.retrieval_top_k

    id_to_filename = {doc.id: doc.filename for doc in await postgres_store.list_documents(user.id)}

    results: list[QueryEvalResult] = []
    for entry in entries:
        try:
            results.append(await _evaluate_entry(entry, id_to_filename, k, user))
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
    entry: GoldenEntry, id_to_filename: dict[str, str], k: int, user: CurrentUser
) -> QueryEvalResult:
    filename_to_id = {filename: document_id for document_id, filename in id_to_filename.items()}
    expected_document_id = (
        filename_to_id.get(entry.expected_document_filename)
        if entry.expected_document_filename
        else None
    )

    # Rerank pinned off: this report measures guardrails and the hybrid baseline; the
    # reranker's effect is measured separately (and on the same pool) by
    # eval/rerank_comparison.py.
    chunks = [chunk async for chunk in run_retrieval(entry.query, user, rerank_enabled=False)]
    body = b"".join(chunks).decode("utf-8")
    answer_text, _, payload_json = body.partition(CITATIONS_MARKER)
    payload = json.loads(payload_json)
    guardrails = [GuardrailVerdict.model_validate(item) for item in payload["guardrails"]]
    blocked = any(verdict.verdict in BLOCKED_VERDICTS for verdict in guardrails)

    matched_rank = None
    if entry.category == "real" and entry.expected_document_filename and expected_document_id:
        candidates = await retrieve_candidates(entry.query, user, top_k=k)
        matched_rank = find_relevant_rank(
            candidates.chunks, id_to_filename, entry.expected_document_filename
        )

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
