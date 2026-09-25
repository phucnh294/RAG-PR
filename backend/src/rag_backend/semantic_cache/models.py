from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CacheCandidate:
    """A cached answer near the question, with its cosine similarity to it.

    citations / evidence are the JSON dumps of the original response's Citation list and
    EvidenceSummary, replayed as-is on a hit.
    """

    id: str
    question: str
    answer: str
    citations: list[dict[str, Any]]
    evidence: dict[str, Any]
    cited_document_ids: list[str]
    similarity: float


@dataclass(frozen=True)
class NewCacheEntry:
    """Everything stored for one cacheable answer."""

    question: str
    embedding: list[float]
    answer: str
    citations: list[dict[str, Any]]
    evidence: dict[str, Any]
    cited_document_ids: list[str]
    access_scope: list[str]
    llm_model_name: str
    embedding_model_name: str
    created_by: str
    ttl_seconds: int
