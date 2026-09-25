"""Semantic cache lookup/store with the permission lock.

A cached answer is served to a user only when BOTH hold:

1. Same access scope: the entry was answered for a user whose allowed classifications
   were exactly the asker's. A higher-clearance user never gets an answer built from a
   narrower corpus, and a lower-clearance user never matches an entry built from
   documents they can't see.
2. Live document check: the asker can read every cited document RIGHT NOW (through
   v_user_accessible_documents), so a revoked grant, a deactivated user or a deleted
   document is never served from a stale entry.

Invalidation (on upload / delete) only keeps answers fresh; correctness never depends on it.
"""

from __future__ import annotations

import logging

import asyncpg

from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.exceptions import SemanticCacheError
from rag_backend.semantic_cache import repository
from rag_backend.semantic_cache.models import CacheCandidate, NewCacheEntry

logger = logging.getLogger(__name__)

# What a DB outage looks like from asyncpg: server errors, a closed/unset pool, sockets.
_DB_ERRORS = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError)


def access_scope(user: CurrentUser) -> list[str]:
    """The user's cache partition key: their allowed classifications, sorted."""
    return sorted(user.allowed_classifications)


def answer_model_name() -> str:
    """The answer LLM that produced an entry — switching models must not replay answers
    another model wrote."""
    if settings.llm_provider == "google":
        return f"google:{settings.google_model_name}"
    return f"{settings.llm_provider}:{settings.llm_model_name}"


async def _can_read_all(user: CurrentUser, document_ids: list[str]) -> bool:
    wanted = set(document_ids)
    if not wanted:
        return False
    readable = await postgres_store.count_accessible_documents(sorted(wanted), user.id)
    return readable == len(wanted)


async def lookup(embedding: list[float], user: CurrentUser) -> CacheCandidate | None:
    """The nearest cached answer the user may be served, or None.

    Raises SemanticCacheError when the cache table can't be read (the pipeline treats
    that as a miss).
    """
    try:
        candidates = await repository.find_cache_candidates(
            embedding,
            access_scope(user),
            answer_model_name(),
            settings.embedding_model_name,
            settings.cache_candidate_k,
        )
        for candidate in candidates:
            if candidate.similarity < settings.cache_min_similarity:
                break
            if await _can_read_all(user, candidate.cited_document_ids):
                await repository.increment_cache_hit(candidate.id)
                return candidate
            logger.info(
                "Cache entry %s skipped: user=%s can no longer read every cited document",
                candidate.id,
                user.username,
            )
    except _DB_ERRORS as error:
        raise SemanticCacheError(f"semantic cache lookup failed: {error}") from error
    return None


async def store(
    question: str,
    embedding: list[float],
    answer: str,
    citations: list[dict[str, object]],
    evidence: dict[str, object],
    user: CurrentUser,
) -> str:
    """Cache an answer under the asker's access scope; returns the new entry id.

    Raises SemanticCacheError when the entry can't be written.
    """
    cited_document_ids = sorted({str(citation["document_id"]) for citation in citations})
    entry = NewCacheEntry(
        question=question,
        embedding=embedding,
        answer=answer,
        citations=citations,
        evidence=evidence,
        cited_document_ids=cited_document_ids,
        access_scope=access_scope(user),
        llm_model_name=answer_model_name(),
        embedding_model_name=settings.embedding_model_name,
        created_by=user.id,
        ttl_seconds=settings.cache_ttl_seconds,
    )
    try:
        return await repository.insert_cache_entry(entry)
    except _DB_ERRORS as error:
        raise SemanticCacheError(f"semantic cache store failed: {error}") from error


async def invalidate_document(document_id: str) -> None:
    """Drop entries citing a deleted document. Never raises: a failure only leaves
    entries that the live document check already refuses to serve."""
    try:
        dropped = await repository.delete_cache_for_document(document_id)
    except _DB_ERRORS as error:
        logger.warning("Cache invalidation failed for document %s: %s", document_id, error)
        return
    if dropped:
        logger.info("Cache: dropped %d entries citing document %s", dropped, document_id)


async def invalidate_classification(classification: str) -> None:
    """Drop entries from every scope that can read a newly indexed document's
    classification — their answers were built without it. Never raises."""
    try:
        dropped = await repository.delete_cache_for_classification(classification)
    except _DB_ERRORS as error:
        logger.warning("Cache invalidation failed for classification %s: %s", classification, error)
        return
    if dropped:
        logger.info("Cache: dropped %d entries readable at %s", dropped, classification)


async def clear() -> int:
    try:
        return await repository.clear_cache()
    except _DB_ERRORS as error:
        raise SemanticCacheError(f"semantic cache clear failed: {error}") from error
