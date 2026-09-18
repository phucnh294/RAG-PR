from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_backend.config import settings
from rag_backend.main import create_app
from rag_backend.storage import dummy_store


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(settings, "input_dir", tmp_path)
    dummy_store._documents.clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
