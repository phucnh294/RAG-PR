"""In-memory fake for the document/chunk store.

This is NOT used in production (see rag_backend.db.postgres_store for the real
Postgres-backed implementation) — it exists purely as a fast, dependency-free test
double. The test suite's root conftest.py monkeypatches every function on
rag_backend.db.postgres_store to point at the matching function here, so pipeline
code always calls "postgres_store.xxx(...)" while tests transparently exercise
this in-memory version instead of a real database.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import UTC, datetime

from rag_backend.config import settings
from rag_backend.storage.records import ChunkRecord, DocumentRecord
from rag_backend.storage.seed_data import SEED_DOCS

_documents: dict[str, DocumentRecord] = {}
_chunks: dict[str, list[ChunkRecord]] = {}


async def list_documents() -> list[DocumentRecord]:
    return sorted(_documents.values(), key=lambda doc: doc.created_at, reverse=True)


async def get_document(document_id: str) -> DocumentRecord | None:
    return _documents.get(document_id)


async def find_by_hash(content_hash: str) -> DocumentRecord | None:
    return next((doc for doc in _documents.values() if doc.content_hash == content_hash), None)


async def add_document(
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


async def update_document(
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


async def delete_document(document_id: str) -> bool:
    _chunks.pop(document_id, None)
    return _documents.pop(document_id, None) is not None


async def add_chunks(document_id: str, chunks: list[ChunkRecord]) -> None:
    _chunks[document_id] = chunks


async def get_chunks(document_id: str) -> list[ChunkRecord]:
    return _chunks.get(document_id, [])


async def all_chunks() -> list[ChunkRecord]:
    """Every stored chunk across every document, used by the retrieval similarity search."""
    return [chunk for chunks in _chunks.values() for chunk in chunks]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def search_similar_chunks(
    embedding: list[float], top_k: int
) -> list[tuple[ChunkRecord, float]]:
    """Rank every stored chunk (across all documents) by cosine similarity, descending.

    Mirrors postgres_store.search_similar_chunks, which does the equivalent ranking
    in SQL via pgvector's `<=>` cosine-distance operator.
    """
    scored = [
        (chunk, _cosine_similarity(embedding, chunk.embedding)) for chunk in await all_chunks()
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


_TERM_PATTERN = re.compile(r"\w+")
# Tiny stand-in for Postgres's english stop-word list — just enough that questions like
# "what is the ..." don't match every chunk through their filler words.
_STOP_WORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from",
        "how", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was",
        "what", "when", "where", "which", "who", "why", "with",
    }
)  # fmt: skip


def _terms(text: str) -> set[str]:
    return {
        term
        for term in _TERM_PATTERN.findall(text.lower())
        if len(term) > 1 and term not in _STOP_WORDS
    }


async def search_fulltext_chunks(
    query_text: str, embedding: list[float], top_k: int
) -> list[tuple[ChunkRecord, float]]:
    """Rank chunks sharing at least one query term by how many distinct terms they share.

    A rough approximation of postgres_store.search_fulltext_chunks (OR-ed plainto_tsquery
    ranked by ts_rank_cd) — no stemming, but the same shape: keyword-matching chunks
    only, each paired with its cosine similarity to `embedding`.
    """
    query_terms = _terms(query_text)
    matches: list[tuple[ChunkRecord, int]] = []
    for chunk in await all_chunks():
        overlap = len(query_terms & _terms(chunk.content))
        if overlap:
            matches.append((chunk, overlap))
    matches.sort(key=lambda item: item[1], reverse=True)
    return [(chunk, _cosine_similarity(embedding, chunk.embedding)) for chunk, _ in matches[:top_k]]


async def ensure_fulltext_index() -> None:
    """No-op: the in-memory store tokenizes chunk content on every search."""


async def seed() -> None:
    """Populate the store with fake documents, run them through the real indexing
    pipeline (so retrieval has real chunk/embedding records to search), and write
    their raw text to data/input/.

    Imports run_indexing locally to avoid a circular import: pipeline.py imports
    this module (via postgres_store) at top level, so this module cannot import
    pipeline.py at top level.
    """
    from rag_backend.rag_pipeline.indexing.pipeline import run_indexing

    if _documents:
        return
    settings.input_dir.mkdir(parents=True, exist_ok=True)
    for seed_doc in SEED_DOCS:
        record = await add_document(
            filename=seed_doc["filename"],
            content_hash=f"seed-{seed_doc['filename']}",
            mime_type="text/markdown" if seed_doc["filename"].endswith(".md") else "text/plain",
            size_bytes=len(seed_doc["content"].encode("utf-8")),
        )
        doc_dir = settings.input_dir / record.id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / record.filename).write_text(seed_doc["content"], encoding="utf-8")
        await run_indexing(record.id, record.filename, record.mime_type)
