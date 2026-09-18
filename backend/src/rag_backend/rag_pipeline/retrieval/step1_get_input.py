from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RawQuery:
    text: str
    document_ids: list[str] | None = None


def get_input(message: str, document_ids: list[str] | None = None) -> RawQuery:
    """Wrap the incoming chat message (and optional document-id filter) as the pipeline's input."""
    return RawQuery(text=message, document_ids=document_ids)
