from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DocumentRecord:
    id: str
    filename: str
    content_hash: str
    mime_type: str
    size_bytes: int
    status: str
    created_at: datetime
    excerpts: list[str] = field(default_factory=list)
    error_message: str | None = None
    classification: str = ""
    created_by: str | None = None
    created_by_username: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ChunkRecord:
    id: str
    document_id: str
    chunk_index: int
    content: str
    embedding: list[float]
    metadata: dict[str, Any]
    # Filled by the permission-scoped searches (from the document's classification) so
    # retrieval can double-check every hit against the caller's allowed classifications.
    classification: str | None = None
