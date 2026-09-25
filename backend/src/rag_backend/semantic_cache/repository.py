"""Postgres-backed semantic cache (the semantic_cache table, created by db/chat_schema.py).

The test suite swaps these functions for the in-memory versions in
storage/dummy_store.py (see tests/conftest.py).
"""

from __future__ import annotations

import uuid

import asyncpg

from rag_backend.db.session import get_pool
from rag_backend.semantic_cache.models import CacheCandidate, NewCacheEntry


def _row_to_candidate(row: asyncpg.Record) -> CacheCandidate:
    return CacheCandidate(
        id=str(row["id"]),
        question=row["question"],
        answer=row["answer"],
        citations=row["citations"],
        evidence=row["evidence"],
        cited_document_ids=[str(document_id) for document_id in row["cited_document_ids"]],
        similarity=float(row["similarity"]),
    )


async def find_cache_candidates(
    embedding: list[float],
    access_scope: list[str],
    llm_model_name: str,
    embedding_model_name: str,
    limit: int,
) -> list[CacheCandidate]:
    """Unexpired entries answered under exactly this access scope and these models,
    nearest first. The caller applies the similarity threshold and the live
    document-access check."""
    rows = await get_pool().fetch(
        """
        SELECT id, question, answer, citations, evidence, cited_document_ids,
               1 - (embedding <=> $1::vector) AS similarity
        FROM semantic_cache
        WHERE access_scope = $2::text[]
          AND llm_model_name = $3
          AND embedding_model_name = $4
          AND expires_at > NOW()
        ORDER BY embedding <=> $1::vector
        LIMIT $5
        """,
        embedding,
        access_scope,
        llm_model_name,
        embedding_model_name,
        limit,
    )
    return [_row_to_candidate(row) for row in rows]


async def insert_cache_entry(entry: NewCacheEntry) -> str:
    entry_id = await get_pool().fetchval(
        """
        INSERT INTO semantic_cache
            (question, embedding, answer, citations, evidence, cited_document_ids,
             access_scope, llm_model_name, embedding_model_name, created_by, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6::uuid[], $7::text[], $8, $9, $10,
                NOW() + make_interval(secs => $11))
        RETURNING id
        """,
        entry.question,
        entry.embedding,
        entry.answer,
        entry.citations,
        entry.evidence,
        [uuid.UUID(document_id) for document_id in entry.cited_document_ids],
        entry.access_scope,
        entry.llm_model_name,
        entry.embedding_model_name,
        uuid.UUID(entry.created_by),
        float(entry.ttl_seconds),
    )
    return str(entry_id)


async def increment_cache_hit(entry_id: str) -> None:
    await get_pool().execute(
        "UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = $1", uuid.UUID(entry_id)
    )


async def delete_cache_for_document(document_id: str) -> int:
    """Drop every entry citing the document; returns how many were dropped."""
    result = await get_pool().execute(
        "DELETE FROM semantic_cache WHERE $1::uuid = ANY(cited_document_ids)",
        uuid.UUID(document_id),
    )
    return int(result.split()[-1])


async def delete_cache_for_classification(classification: str) -> int:
    """Drop every entry answered under a scope that can read `classification`."""
    result = await get_pool().execute(
        "DELETE FROM semantic_cache WHERE $1 = ANY(access_scope)", classification
    )
    return int(result.split()[-1])


async def clear_cache() -> int:
    result = await get_pool().execute("DELETE FROM semantic_cache")
    return int(result.split()[-1])
