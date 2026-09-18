from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rag_backend.config import settings


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


_documents: dict[str, DocumentRecord] = {}
_chunks: dict[str, list[ChunkRecord]] = {}


def list_documents() -> list[DocumentRecord]:
    return sorted(_documents.values(), key=lambda doc: doc.created_at, reverse=True)


def get_document(document_id: str) -> DocumentRecord | None:
    return _documents.get(document_id)


def find_by_hash(content_hash: str) -> DocumentRecord | None:
    return next((doc for doc in _documents.values() if doc.content_hash == content_hash), None)


def add_document(
    filename: str,
    content_hash: str,
    mime_type: str,
    size_bytes: int,
    status: str = "pending",
    excerpts: list[str] | None = None,
) -> DocumentRecord:
    record = DocumentRecord(
        id=str(uuid.uuid4()),
        filename=filename,
        content_hash=content_hash,
        mime_type=mime_type,
        size_bytes=size_bytes,
        status=status,
        created_at=datetime.now(UTC),
        excerpts=excerpts or [],
    )
    _documents[record.id] = record
    return record


def update_document(
    document_id: str,
    status: str,
    excerpts: list[str] | None = None,
    error_message: str | None = None,
) -> DocumentRecord | None:
    record = _documents.get(document_id)
    if record is None:
        return None
    record.status = status
    if excerpts is not None:
        record.excerpts = excerpts
    if error_message is not None:
        record.error_message = error_message
    return record


def delete_document(document_id: str) -> bool:
    _chunks.pop(document_id, None)
    return _documents.pop(document_id, None) is not None


def all_excerpts() -> list[tuple[DocumentRecord, str]]:
    """Flat (document, excerpt) pairs across every seeded/uploaded document, used to fake citations."""
    return [(doc, excerpt) for doc in _documents.values() for excerpt in doc.excerpts]


def add_chunks(document_id: str, chunks: list[ChunkRecord]) -> None:
    _chunks[document_id] = chunks


def get_chunks(document_id: str) -> list[ChunkRecord]:
    return _chunks.get(document_id, [])


_SEED_DOCS = [
    {
        "filename": "employee_handbook.md",
        "content": "All employees are entitled to 20 days of paid annual leave per calendar year.",
        "excerpts": [
            "Employees are entitled to 20 days of paid annual leave per calendar year.",
            "Leave requests must be submitted at least 5 business days in advance.",
        ],
    },
    {
        "filename": "product_faq.md",
        "content": "The free tier includes up to 100 API requests per day.",
        "excerpts": [
            "The free tier includes up to 100 API requests per day.",
            "Upgrading to the Pro plan removes the daily request limit.",
        ],
    },
    {
        "filename": "onboarding_guide.txt",
        "content": "New hires should complete security training within their first week.",
        "excerpts": [
            "New hires should complete security training within their first week.",
            "Your manager will assign a buddy for your first 30 days.",
        ],
    },
]


def seed() -> None:
    """Populate the in-memory store with fake documents and write their raw text to data/input/."""
    if _documents:
        return
    settings.input_dir.mkdir(parents=True, exist_ok=True)
    for seed_doc in _SEED_DOCS:
        record = add_document(
            filename=seed_doc["filename"],
            content_hash=f"seed-{seed_doc['filename']}",
            mime_type="text/markdown" if seed_doc["filename"].endswith(".md") else "text/plain",
            size_bytes=len(seed_doc["content"].encode("utf-8")),
            status="ready",
            excerpts=seed_doc["excerpts"],
        )
        doc_dir = settings.input_dir / record.id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / record.filename).write_text(seed_doc["content"], encoding="utf-8")
