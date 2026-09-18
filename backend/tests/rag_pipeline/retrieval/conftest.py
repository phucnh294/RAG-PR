from __future__ import annotations

import pytest

from rag_backend.storage import dummy_store


@pytest.fixture(autouse=True)
def _clear_dummy_store() -> None:
    """Retrieval tests query dummy_store's global state directly, so isolate each
    test from documents/chunks left behind by other test modules in the same run.
    """
    dummy_store._documents.clear()
    dummy_store._chunks.clear()
