from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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


@dataclass
class ChunkRecord:
    id: str
    document_id: str
    chunk_index: int
    content: str
    embedding: list[float]
    metadata: dict[str, int]
