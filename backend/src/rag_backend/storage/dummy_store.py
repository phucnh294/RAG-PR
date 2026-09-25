"""In-memory fake for the document/chunk store and the auth repository.

This is NOT used in production (see rag_backend.db.postgres_store and
rag_backend.auth.repository for the real Postgres-backed implementations) — it exists
purely as a fast, dependency-free test double. The test suite's root conftest.py
monkeypatches every function on postgres_store / auth.repository to point at the
matching function here, so pipeline code always calls "postgres_store.xxx(...)" while
tests transparently exercise this in-memory version instead of a real database.

The user-scoped reads mirror the v_user_accessible_* views exactly: a document is
visible to a user only if the user exists, is active, and the user's role is granted
the document's classification in _access. Chunks inherit their document's visibility.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime

from rag_backend.auth.models import UserRecord
from rag_backend.config import settings
from rag_backend.storage.records import ChunkRecord, DocumentRecord
from rag_backend.storage.seed_data import SEED_DOCS

_documents: dict[str, DocumentRecord] = {}
_chunks: dict[str, list[ChunkRecord]] = {}
_users: dict[str, UserRecord] = {}
_roles: dict[str, int] = {}
_classifications: dict[str, int] = {}
_access: set[tuple[str, str]] = set()
_seeded_grants: set[tuple[str, str]] = set()
# Document fields the real table has but DocumentRecord doesn't expose, keyed by doc id.
_document_extras: dict[str, dict[str, object]] = {}


def reset() -> None:
    for store in (_documents, _chunks, _users, _roles, _classifications, _document_extras):
        store.clear()
    _access.clear()
    _seeded_grants.clear()


# --- permission view equivalents ---


def _readable_classifications(user_id: str) -> set[str]:
    user = _users.get(user_id)
    if user is None or not user.is_active:
        return set()
    return {classification for role, classification in _access if role == user.role}


def _with_creator(document: DocumentRecord) -> DocumentRecord:
    creator = _users.get(document.created_by or "")
    return replace(document, created_by_username=creator.username if creator else None)


def _visible_chunks(user_id: str) -> list[ChunkRecord]:
    readable = _readable_classifications(user_id)
    visible: list[ChunkRecord] = []
    for document_id, chunks in _chunks.items():
        document = _documents.get(document_id)
        if document is not None and document.classification in readable:
            visible.extend(
                replace(chunk, classification=document.classification) for chunk in chunks
            )
    return visible


# --- documents ---


async def list_documents(user_id: str) -> list[DocumentRecord]:
    readable = _readable_classifications(user_id)
    visible = [doc for doc in _documents.values() if doc.classification in readable]
    return [
        _with_creator(doc) for doc in sorted(visible, key=lambda doc: doc.created_at, reverse=True)
    ]


async def get_document(document_id: str, user_id: str) -> DocumentRecord | None:
    document = _documents.get(document_id)
    if document is None or document.classification not in _readable_classifications(user_id):
        return None
    return _with_creator(document)


async def get_document_unscoped(document_id: str) -> DocumentRecord | None:
    document = _documents.get(document_id)
    return _with_creator(document) if document is not None else None


async def find_existing(
    classification: str, content_hash: str, created_by: str | None
) -> DocumentRecord | None:
    return next(
        (
            doc
            for doc in _documents.values()
            if doc.classification == classification
            and doc.content_hash == content_hash
            and doc.created_by == created_by
        ),
        None,
    )


async def add_document(
    filename: str,
    content_hash: str,
    mime_type: str,
    size_bytes: int,
    status: str = "pending",
    excerpts: list[str] | None = None,
    classification: str | None = None,
    created_by: str | None = None,
    tags: list[str] | None = None,
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
        classification=classification or settings.auth_default_classification,
        created_by=created_by,
        tags=list(tags or []),
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


async def update_document_metadata(
    document_id: str,
    doc_date: date | None = None,
    area: str | None = None,
    tags: list[str] | None = None,
    summary: str | None = None,
    description: str | None = None,
) -> None:
    record = _documents.get(document_id)
    if record is None:
        return
    record.tags = list(dict.fromkeys([*record.tags, *(tags or [])]))
    extras = _document_extras.setdefault(document_id, {})
    for key, value in (
        ("doc_date", doc_date),
        ("area", area),
        ("summary", summary),
        ("description", description),
    ):
        if value is not None:
            extras[key] = value


async def delete_document(document_id: str) -> bool:
    _chunks.pop(document_id, None)
    _document_extras.pop(document_id, None)
    return _documents.pop(document_id, None) is not None


async def add_chunks(document_id: str, chunks: list[ChunkRecord]) -> None:
    _chunks[document_id] = chunks


async def get_chunks(document_id: str) -> list[ChunkRecord]:
    return _chunks.get(document_id, [])


async def all_chunks() -> list[ChunkRecord]:
    """Every stored chunk across every document, regardless of permissions."""
    return [chunk for chunks in _chunks.values() for chunk in chunks]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def search_similar_chunks(
    embedding: list[float], top_k: int, user_id: str
) -> list[tuple[ChunkRecord, float]]:
    """Rank the user's visible chunks by cosine similarity, descending.

    Mirrors postgres_store.search_similar_chunks, which does the equivalent ranking
    in SQL via pgvector's `<=>` cosine-distance operator over v_user_accessible_chunks.
    """
    scored = [
        (chunk, _cosine_similarity(embedding, chunk.embedding))
        for chunk in _visible_chunks(user_id)
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
    query_text: str, embedding: list[float], top_k: int, user_id: str
) -> list[tuple[ChunkRecord, float]]:
    """Rank the user's visible chunks sharing at least one query term by how many
    distinct terms they share.

    A rough approximation of postgres_store.search_fulltext_chunks (OR-ed plainto_tsquery
    ranked by ts_rank_cd) — no stemming, but the same shape: keyword-matching chunks
    only, each paired with its cosine similarity to `embedding`.
    """
    query_terms = _terms(query_text)
    matches: list[tuple[ChunkRecord, int]] = []
    for chunk in _visible_chunks(user_id):
        overlap = len(query_terms & _terms(chunk.content))
        if overlap:
            matches.append((chunk, overlap))
    matches.sort(key=lambda item: item[1], reverse=True)
    return [(chunk, _cosine_similarity(embedding, chunk.embedding)) for chunk, _ in matches[:top_k]]


async def ensure_fulltext_index() -> None:
    """No-op: the in-memory store tokenizes chunk content on every search."""


async def seed(created_by: str) -> None:
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
            classification=settings.seed_documents_classification,
            created_by=created_by,
        )
        doc_dir = settings.input_dir / record.id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / record.filename).write_text(seed_doc["content"], encoding="utf-8")
        await run_indexing(record.id, record.filename, record.mime_type)


# --- auth repository equivalents (see rag_backend.auth.repository) ---


async def ensure_role(name: str, rank: int) -> bool:
    if name in _roles:
        return False
    _roles[name] = rank
    return True


async def ensure_classification(name: str, level: int) -> bool:
    if name in _classifications:
        return False
    _classifications[name] = level
    return True


async def list_roles() -> list[str]:
    return sorted(_roles, key=_roles.__getitem__)


async def list_classifications() -> list[str]:
    return sorted(_classifications, key=_classifications.__getitem__)


async def get_user(user_id: str) -> UserRecord | None:
    return _users.get(user_id)


async def get_user_by_username(username: str) -> UserRecord | None:
    return next((user for user in _users.values() if user.username == username), None)


async def list_users() -> list[UserRecord]:
    return sorted(_users.values(), key=lambda user: (_roles.get(user.role, 0), user.username))


async def create_user(username: str, display_name: str | None, role: str) -> UserRecord:
    user = UserRecord(
        id=str(uuid.uuid4()),
        username=username,
        display_name=display_name,
        role=role,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    _users[user.id] = user
    return user


async def upsert_user(username: str, display_name: str | None, role: str) -> UserRecord:
    existing = await get_user_by_username(username)
    if existing is None:
        return await create_user(username, display_name, role)
    updated = replace(existing, role=role, is_active=True)
    _users[updated.id] = updated
    return updated


async def set_user_role(user_id: str, role: str) -> UserRecord | None:
    user = _users.get(user_id)
    if user is None:
        return None
    _users[user_id] = replace(user, role=role)
    return _users[user_id]


async def set_user_active(user_id: str, is_active: bool) -> UserRecord | None:
    user = _users.get(user_id)
    if user is None:
        return None
    _users[user_id] = replace(user, is_active=is_active)
    return _users[user_id]


async def get_allowed_classifications(role: str) -> list[str]:
    granted = {classification for granted_role, classification in _access if granted_role == role}
    return [name for name in await list_classifications() if name in granted]


async def list_access() -> dict[str, list[str]]:
    matrix: dict[str, list[str]] = {}
    for role in await list_roles():
        allowed = await get_allowed_classifications(role)
        if allowed:
            matrix[role] = allowed
    return matrix


async def grant_access(role: str, classification: str, granted_by: str | None) -> bool:
    if (role, classification) in _access:
        return False
    _access.add((role, classification))
    return True


async def mark_grant_seeded(role: str, classification: str) -> bool:
    if (role, classification) in _seeded_grants:
        return False
    _seeded_grants.add((role, classification))
    return True


async def revoke_access(role: str, classification: str) -> bool:
    if (role, classification) not in _access:
        return False
    _access.discard((role, classification))
    return True
