from __future__ import annotations

import json
import logging

import asyncpg

from rag_backend.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _encode_vector(value: list[float]) -> str:
    return "[" + ",".join(str(float(component)) for component in value) + "]"


def _decode_vector(value: str) -> list[float]:
    stripped = value.strip("[]")
    return [float(component) for component in stripped.split(",")] if stripped else []


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register codecs so asyncpg can round-trip pgvector's vector type and jsonb
    as plain Python list[float]/dict, without pulling in the pgvector/numpy packages.
    """
    await conn.set_type_codec(
        "vector",
        encoder=_encode_vector,
        decoder=_decode_vector,
        schema="public",
        format="text",
    )
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def init_pool() -> None:
    """Create the shared connection pool. Safe to call more than once."""
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
        init=_init_connection,
        min_size=1,
        max_size=10,
    )
    logger.info(
        "Postgres connection pool initialized (%s:%s/%s)",
        settings.postgres_host,
        settings.postgres_port,
        settings.postgres_db,
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Postgres connection pool is not initialized; call init_pool() first")
    return _pool
