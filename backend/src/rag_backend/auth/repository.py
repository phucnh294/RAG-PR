"""Postgres access for users, roles, classifications and the role->classification matrix.

Tests route every function here to the in-memory rag_backend.storage.dummy_store (see
tests/conftest.py), so callers must always go through `repository.<name>(...)`.
"""

from __future__ import annotations

import uuid

import asyncpg

from rag_backend.auth.models import UserRecord
from rag_backend.db.session import get_pool


def _row_to_user(row: asyncpg.Record) -> UserRecord:
    return UserRecord(
        id=str(row["id"]),
        username=row["username"],
        display_name=row["display_name"],
        role=row["role"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    )


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def ensure_role(name: str, rank: int) -> bool:
    """Insert the role if it is missing. Returns True when a row was inserted."""
    result = await get_pool().execute(
        "INSERT INTO roles (name, rank) VALUES ($1, $2) ON CONFLICT (name) DO NOTHING",
        name,
        rank,
    )
    return result == "INSERT 0 1"


async def ensure_classification(name: str, level: int) -> bool:
    """Insert the classification if it is missing. Returns True when a row was inserted."""
    result = await get_pool().execute(
        "INSERT INTO document_classifications (name, level) VALUES ($1, $2) "
        "ON CONFLICT (name) DO NOTHING",
        name,
        level,
    )
    return result == "INSERT 0 1"


async def list_roles() -> list[str]:
    rows = await get_pool().fetch("SELECT name FROM roles ORDER BY rank")
    return [row["name"] for row in rows]


async def list_classifications() -> list[str]:
    rows = await get_pool().fetch("SELECT name FROM document_classifications ORDER BY level")
    return [row["name"] for row in rows]


async def get_user(user_id: str) -> UserRecord | None:
    user_uuid = _as_uuid(user_id)
    if user_uuid is None:
        return None
    row = await get_pool().fetchrow("SELECT * FROM users WHERE id = $1", user_uuid)
    return _row_to_user(row) if row is not None else None


async def get_user_by_username(username: str) -> UserRecord | None:
    row = await get_pool().fetchrow("SELECT * FROM users WHERE username = $1", username)
    return _row_to_user(row) if row is not None else None


async def list_users() -> list[UserRecord]:
    rows = await get_pool().fetch(
        "SELECT u.* FROM users u JOIN roles r ON r.name = u.role ORDER BY r.rank, u.username"
    )
    return [_row_to_user(row) for row in rows]


async def create_user(username: str, display_name: str | None, role: str) -> UserRecord:
    row = await get_pool().fetchrow(
        "INSERT INTO users (username, display_name, role) VALUES ($1, $2, $3) RETURNING *",
        username,
        display_name,
        role,
    )
    assert row is not None
    return _row_to_user(row)


async def upsert_user(username: str, display_name: str | None, role: str) -> UserRecord:
    """Create the user, or force an existing one back to `role` and active (used by seeding)."""
    row = await get_pool().fetchrow(
        """
        INSERT INTO users (username, display_name, role) VALUES ($1, $2, $3)
        ON CONFLICT (username) DO UPDATE
            SET role = EXCLUDED.role, is_active = TRUE, updated_at = NOW()
        RETURNING *
        """,
        username,
        display_name,
        role,
    )
    assert row is not None
    return _row_to_user(row)


async def set_user_role(user_id: str, role: str) -> UserRecord | None:
    user_uuid = _as_uuid(user_id)
    if user_uuid is None:
        return None
    row = await get_pool().fetchrow(
        "UPDATE users SET role = $2, updated_at = NOW() WHERE id = $1 RETURNING *",
        user_uuid,
        role,
    )
    return _row_to_user(row) if row is not None else None


async def set_user_active(user_id: str, is_active: bool) -> UserRecord | None:
    user_uuid = _as_uuid(user_id)
    if user_uuid is None:
        return None
    row = await get_pool().fetchrow(
        "UPDATE users SET is_active = $2, updated_at = NOW() WHERE id = $1 RETURNING *",
        user_uuid,
        is_active,
    )
    return _row_to_user(row) if row is not None else None


async def get_allowed_classifications(role: str) -> list[str]:
    rows = await get_pool().fetch(
        """
        SELECT a.classification
        FROM role_classification_access a
        JOIN document_classifications c ON c.name = a.classification
        WHERE a.role = $1
        ORDER BY c.level
        """,
        role,
    )
    return [row["classification"] for row in rows]


async def list_access() -> dict[str, list[str]]:
    rows = await get_pool().fetch("""
        SELECT a.role, a.classification
        FROM role_classification_access a
        JOIN roles r ON r.name = a.role
        JOIN document_classifications c ON c.name = a.classification
        ORDER BY r.rank, c.level
        """)
    matrix: dict[str, list[str]] = {}
    for row in rows:
        matrix.setdefault(row["role"], []).append(row["classification"])
    return matrix


async def grant_access(role: str, classification: str, granted_by: str | None) -> bool:
    """Grant `role` read access to `classification`. Returns True when newly granted."""
    result = await get_pool().execute(
        """
        INSERT INTO role_classification_access (role, classification, granted_by)
        VALUES ($1, $2, $3)
        ON CONFLICT (role, classification) DO NOTHING
        """,
        role,
        classification,
        _as_uuid(granted_by) if granted_by else None,
    )
    return result == "INSERT 0 1"


async def mark_grant_seeded(role: str, classification: str) -> bool:
    """Record that the config grant was applied. Returns True the first time only."""
    result = await get_pool().execute(
        "INSERT INTO authz_seeded_grants (role, classification) VALUES ($1, $2) "
        "ON CONFLICT (role, classification) DO NOTHING",
        role,
        classification,
    )
    return result == "INSERT 0 1"


async def revoke_access(role: str, classification: str) -> bool:
    """Revoke the grant. Returns True when a grant existed."""
    result = await get_pool().execute(
        "DELETE FROM role_classification_access WHERE role = $1 AND classification = $2",
        role,
        classification,
    )
    return result == "DELETE 1"
