from __future__ import annotations

from pathlib import Path

import pytest

from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.storage import dummy_store


@pytest.fixture
async def seeded_corpus(
    auth_users: dict[str, CurrentUser], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Index the built-in seed documents (as app startup does), so golden-set entries
    that target them resolve to real, searchable documents."""
    monkeypatch.setattr(settings, "input_dir", tmp_path / "input")
    await dummy_store.seed(auth_users["admin"].id)
