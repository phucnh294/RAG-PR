"""Idempotent authorization schema: roles, users, classifications, the role->classification
access matrix, the new rag_documents ownership columns, and the permission views.

Runs at every startup (like postgres_store.ensure_fulltext_index) because
postgres/init/*.sql only runs on a fresh volume. Split in two phases because the
ownership backfill needs the seeded admin's id:

1. ensure_authorization_schema()  — tables, nullable columns, views.
2. finalize_document_ownership()  — backfill old rows, then NOT NULL + unique dedup key.

The views are the permission gate: every user-facing read of documents/chunks goes
through them filtered by user_id, so the access rule lives in exactly one SQL join. An
unknown or inactive user matches zero rows — the gate fails closed.
"""

from __future__ import annotations

import logging
import uuid

from rag_backend.db.session import get_pool

logger = logging.getLogger(__name__)

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS roles (
    name        VARCHAR(50) PRIMARY KEY,
    rank        INT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username     VARCHAR(100) NOT NULL UNIQUE,
    display_name TEXT,
    role         VARCHAR(50) NOT NULL REFERENCES roles(name),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS users_role_idx ON users (role);

CREATE TABLE IF NOT EXISTS document_classifications (
    name        VARCHAR(50) PRIMARY KEY,
    level       INT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS role_classification_access (
    role           VARCHAR(50) NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
    classification VARCHAR(50) NOT NULL
                   REFERENCES document_classifications(name) ON DELETE CASCADE,
    granted_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    granted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role, classification)
);

-- Which config (AUTH_ROLE_ACCESS) grants have already been applied once. Lets startup
-- add grants that are NEW in config without resurrecting grants an admin revoked.
CREATE TABLE IF NOT EXISTS authz_seeded_grants (
    role           VARCHAR(50) NOT NULL,
    classification VARCHAR(50) NOT NULL,
    seeded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role, classification)
);

ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS classification VARCHAR(50)
    REFERENCES document_classifications(name);
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS created_by UUID
    REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS content_hash TEXT;
CREATE INDEX IF NOT EXISTS rag_documents_classification_idx ON rag_documents (classification);
"""

# Dropped and recreated every startup: CREATE OR REPLACE VIEW cannot change an existing
# view's column list, and these views have no state of their own.
_VIEWS_SQL = """
DROP VIEW IF EXISTS v_user_accessible_chunks;
DROP VIEW IF EXISTS v_user_accessible_documents;

CREATE VIEW v_user_accessible_documents AS
SELECT u.id              AS user_id,
       u.role            AS user_role,
       d.id, d.source_path, d.doc_type, d.title, d.doc_date, d.area, d.status, d.tags,
       d.description, d.summary, d.metadata, d.created_at,
       d.classification, d.created_by, d.content_hash,
       creator.username  AS created_by_username
FROM users u
JOIN role_classification_access a ON a.role = u.role
JOIN rag_documents d              ON d.classification = a.classification
LEFT JOIN users creator           ON creator.id = d.created_by
WHERE u.is_active;

CREATE VIEW v_user_accessible_chunks AS
SELECT vd.user_id,
       vd.classification,
       c.id, c.document_id, c.chunk_index, c.content, c.metadata, c.content_tsv,
       e.embedding
FROM v_user_accessible_documents vd
JOIN rag_chunks c     ON c.document_id = vd.id
JOIN rag_embeddings e ON e.chunk_id = c.id;
"""


async def ensure_authorization_schema() -> None:
    """Create the authorization tables/columns and (re)create the permission views."""
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(_TABLES_SQL)
        await conn.execute(_VIEWS_SQL)
    logger.info("Authorization schema ready (tables, rag_documents columns, permission views)")


async def finalize_document_ownership(admin_user_id: str, default_classification: str) -> None:
    """Backfill documents created before authorization existed, then lock the columns down.

    Old rows get the default classification and the seeded admin as creator; content_hash
    moves out of the metadata jsonb into its own column so the dedup key can index it.
    """
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        result = await conn.execute(
            """
            UPDATE rag_documents
            SET classification = COALESCE(classification, $2),
                created_by     = COALESCE(created_by, $1::uuid),
                content_hash   = COALESCE(content_hash, metadata ->> 'content_hash')
            WHERE classification IS NULL OR created_by IS NULL OR content_hash IS NULL
            """,
            uuid.UUID(admin_user_id),
            default_classification,
        )
        await conn.execute("ALTER TABLE rag_documents ALTER COLUMN classification SET NOT NULL")
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS rag_documents_dedup_key "
            "ON rag_documents (classification, content_hash, created_by)"
        )
    logger.info("Document ownership finalized (backfill: %s)", result)
