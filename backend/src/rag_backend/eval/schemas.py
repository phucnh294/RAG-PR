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
