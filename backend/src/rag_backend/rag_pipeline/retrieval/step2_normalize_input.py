from __future__ import annotations

import re
from dataclasses import dataclass

from rag_backend.rag_pipeline.retrieval.step1_get_input import RawQuery

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class NormalizedQuery:
    text: str
    document_ids: list[str] | None = None


def normalize_input(raw_query: RawQuery) -> NormalizedQuery:
    """Collapse whitespace and strip the raw query text before embedding it."""
    normalized_text = _WHITESPACE_RE.sub(" ", raw_query.text).strip()
    return NormalizedQuery(text=normalized_text, document_ids=raw_query.document_ids)
