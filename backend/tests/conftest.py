from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.db import session as db_session
from rag_backend.main import create_app
from rag_backend.storage import dummy_store

_STORE_FUNCTIONS = (
    "list_documents",
    "get_document",
    "find_by_hash",
    "add_document",
    "update_document",
    "delete_document",
    "add_chunks",
    "get_chunks",
    "all_chunks",
    "search_similar_chunks",
    "seed",
)


async def _noop_pool_lifecycle() -> None:
    return None


@pytest.fixture(autouse=True)
def _fake_postgres_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route every rag_backend.db.postgres_store call to the in-memory dummy_store.

    Pipeline/route code always calls "postgres_store.xxx(...)" — this makes tests
    exercise that exact code path without needing a live Postgres connection.
    """
    for name in _STORE_FUNCTIONS:
        monkeypatch.setattr(postgres_store, name, getattr(dummy_store, name))
    monkeypatch.setattr(db_session, "init_pool", _noop_pool_lifecycle)
    monkeypatch.setattr(db_session, "close_pool", _noop_pool_lifecycle)
    dummy_store._documents.clear()
    dummy_store._chunks.clear()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(settings, "input_dir", tmp_path)
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
