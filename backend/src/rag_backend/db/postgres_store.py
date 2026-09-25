"""Real Postgres-backed document/chunk store.

Persists into the rag_documents / rag_chunks / rag_embeddings tables created by
postgres/init/01-create-extension.sql. This schema's columns (source_path, title,
doc_type, status, metadata jsonb, ...) were originally shaped for embedding the
project's own rag-ai-local/*.md knowledge base, but are generic enough to reuse
for app-uploaded documents too:
  - source_path  -> data/input/<document_id>/<filename> (always unique per upload)
  - title        -> original filename
  - doc_type     -> mime type
  - metadata     -> {content_hash, size_bytes, excerpts, error_message}, since the
                     table has no dedicated columns for those upload-specific fields
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import asyncpg

from rag_backend.config import settings
from rag_backend.db.session import get_pool
from rag_backend.storage.records import ChunkRecord, DocumentRecord
from rag_backend.storage.seed_data import SEED_DOCS

logger = logging.getLogger(__name__)


def _row_to_document(row: asyncpg.Record) -> DocumentRecord:
    metadata: dict[str, Any] = row["metadata"] or {}
    return DocumentRecord(
        id=str(row["id"]),
        filename=row["title"] or "",
        content_hash=metadata.get("content_hash", ""),
        mime_type=row["doc_type"] or "",
        size_bytes=metadata.get("size_bytes", 0),
        status=row["status"] or "pending",
        created_at=row["created_at"],
        excerpts=metadata.get("excerpts", []),
        error_message=metadata.get("error_message"),
    )


def _row_to_chunk(row: asyncpg.Record) -> ChunkRecord:
    embedding = row["embedding"]
    return ChunkRecord(
        id=str(row["id"]),
        document_id=str(row["document_id"]),
        chunk_index=row["chunk_index"],
        content=row["content"],
        embedding=list(embedding) if embedding is not None else [],
        metadata=row["metadata"] or {},
    )


async def list_documents() -> list[DocumentRecord]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM rag_documents ORDER BY created_at DESC")
    return [_row_to_document(row) for row in rows]


async def get_document(document_id: str) -> DocumentRecord | None:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM rag_documents WHERE id = $1", uuid.UUID(document_id))
    return _row_to_document(row) if row is not None else None


async def find_by_hash(content_hash: str) -> DocumentRecord | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM rag_documents WHERE metadata ->> 'content_hash' = $1", content_hash
    )
    return _row_to_document(row) if row is not None else None


async def add_document(
    filename: str,
    content_hash: str,
    mime_type: str,
    size_bytes: int,
    status: str = "pending",
    excerpts: list[str] | None = None,
) -> DocumentRecord:
    pool = get_pool()
    document_id = uuid.uuid4()
    metadata = {
        "content_hash": content_hash,
        "size_bytes": size_bytes,
        "excerpts": excerpts or [],
    }
    row = await pool.fetchrow(
        """
        INSERT INTO rag_documents (id, source_path, doc_type, title, status, metadata)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        document_id,
        f"data/input/{document_id}/{filename}",
        mime_type,
        filename,
        status,
        metadata,
    )
    assert row is not None
    return _row_to_document(row)


async def update_document(
    document_id: str,
    status: str,
    excerpts: list[str] | None = None,
    error_message: str | None = None,
) -> DocumentRecord | None:
    pool = get_pool()
    doc_uuid = uuid.UUID(document_id)
    existing = await pool.fetchrow("SELECT metadata FROM rag_documents WHERE id = $1", doc_uuid)
    if existing is None:
        return None
    metadata: dict[str, Any] = dict(existing["metadata"] or {})
    if excerpts is not None:
        metadata["excerpts"] = excerpts
    if error_message is not None:
        metadata["error_message"] = error_message
    row = await pool.fetchrow(
        "UPDATE rag_documents SET status = $2, metadata = $3 WHERE id = $1 RETURNING *",
        doc_uuid,
        status,
        metadata,
    )
    assert row is not None
    return _row_to_document(row)


async def delete_document(document_id: str) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM rag_documents WHERE id = $1", uuid.UUID(document_id))
    return result == "DELETE 1"


async def add_chunks(document_id: str, chunks: list[ChunkRecord]) -> None:
    """Replace every chunk (and its embedding) belonging to document_id."""
    pool = get_pool()
    doc_uuid = uuid.UUID(document_id)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM rag_chunks WHERE document_id = $1", doc_uuid)
        for chunk in chunks:
            chunk_uuid = uuid.UUID(chunk.id)
            await conn.execute(
                """
                INSERT INTO rag_chunks
                    (id, document_id, chunk_index, content, token_count, metadata, content_tsv)
                VALUES ($1, $2, $3, $4, $5, $6, to_tsvector($7::regconfig, $4))
                """,
                chunk_uuid,
                doc_uuid,
                chunk.chunk_index,
                chunk.content,
                chunk.metadata.get("word_count"),
                chunk.metadata,
                settings.fulltext_search_config,
            )
            await conn.execute(
                "INSERT INTO rag_embeddings (id, chunk_id, embedding, model) VALUES ($1, $2, $3, $4)",
                uuid.uuid4(),
                chunk_uuid,
                chunk.embedding,
                settings.embedding_model_name,
            )


async def get_chunks(document_id: str) -> list[ChunkRecord]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT c.id, c.document_id, c.chunk_index, c.content, c.metadata, e.embedding
        FROM rag_chunks c
        LEFT JOIN rag_embeddings e ON e.chunk_id = c.id
        WHERE c.document_id = $1
        ORDER BY c.chunk_index
        """,
        uuid.UUID(document_id),
    )
    return [_row_to_chunk(row) for row in rows]


async def all_chunks() -> list[ChunkRecord]:
    pool = get_pool()
    rows = await pool.fetch("""
        SELECT c.id, c.document_id, c.chunk_index, c.content, c.metadata, e.embedding
        FROM rag_chunks c
        LEFT JOIN rag_embeddings e ON e.chunk_id = c.id
        """)
    return [_row_to_chunk(row) for row in rows]


async def search_similar_chunks(
    embedding: list[float], top_k: int
) -> list[tuple[ChunkRecord, float]]:
    """Rank chunks by pgvector cosine similarity (1 - cosine distance), descending."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT c.id, c.document_id, c.chunk_index, c.content, c.metadata,
               e.embedding, 1 - (e.embedding <=> $1::vector) AS similarity_score
        FROM rag_chunks c
        JOIN rag_embeddings e ON e.chunk_id = c.id
        ORDER BY e.embedding <=> $1::vector
        LIMIT $2
        """,
        embedding,
        top_k,
    )
    return [(_row_to_chunk(row), float(row["similarity_score"])) for row in rows]


async def search_fulltext_chunks(
    query_text: str, embedding: list[float], top_k: int
) -> list[tuple[ChunkRecord, float]]:
    """Rank chunks by Postgres full-text relevance (ts_rank_cd over content_tsv), descending.

    The question is parsed with plainto_tsquery (stemming + stop-word removal, never a
    syntax error on user input) and its AND operators are rewritten to OR, so a chunk
    matching only some of the question's terms still qualifies — AND would demand every
    term of a natural-language question and almost never match.

    Each row still carries its cosine similarity to `embedding`, so a chunk found only
    by keywords has a real similarity_score for the threshold/evidence steps downstream.
    """
    pool = get_pool()
    rows = await pool.fetch(
        """
        WITH q AS (
            SELECT replace(plainto_tsquery($3::regconfig, $2)::text, '&', '|')::tsquery AS query
        )
        SELECT c.id, c.document_id, c.chunk_index, c.content, c.metadata,
               e.embedding, 1 - (e.embedding <=> $1::vector) AS similarity_score
        FROM rag_chunks c
        JOIN rag_embeddings e ON e.chunk_id = c.id
        CROSS JOIN q
        WHERE c.content_tsv @@ q.query
        ORDER BY ts_rank_cd(c.content_tsv, q.query) DESC
        LIMIT $4
        """,
        embedding,
        query_text,
        settings.fulltext_search_config,
        top_k,
    )
    return [(_row_to_chunk(row), float(row["similarity_score"])) for row in rows]


async def ensure_fulltext_index() -> None:
    """Make sure rag_chunks.content_tsv exists, is GIN-indexed, and is filled.

    postgres/init/*.sql only runs on a fresh volume, so databases created before hybrid
    search need this at startup. Idempotent: the backfill only touches NULL rows.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS rag_chunks_content_tsv_idx "
            "ON rag_chunks USING GIN (content_tsv)"
        )
        result = await conn.execute(
            "UPDATE rag_chunks SET content_tsv = to_tsvector($1::regconfig, content) "
            "WHERE content_tsv IS NULL",
            settings.fulltext_search_config,
        )
    logger.info("Full-text index ready on rag_chunks.content_tsv (backfill: %s)", result)


async def seed() -> None:
    """Populate the database with fake documents (once) and run them through the
    real indexing pipeline, so retrieval has real chunk/embedding rows to search.

    Imports run_indexing locally to avoid a circular import: pipeline.py imports
    this module at top level.
    """
    from rag_backend.rag_pipeline.indexing.pipeline import run_indexing

    if await list_documents():
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
