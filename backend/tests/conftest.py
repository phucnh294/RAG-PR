from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.db import session as db_session
from rag_backend.embedding_model import client as embedding_model_client
from rag_backend.embedding_model import fake_client as fake_embedding_client
from rag_backend.guardrails import judge_client
from rag_backend.llm_model.client import LlmClient
from rag_backend.main import create_app
from rag_backend.storage import dummy_store


class FakeGuardrailJudgeClient(LlmClient):
    """Default guardrail judge double: always reports "safe" without any network call.

    Individual tests override this per-test by monkeypatching
    rag_backend.guardrails.judge_client.guardrail_judge_client again, or by
    subclassing with a different complete_chat to exercise unsafe/judge_error paths.
    """

    def __init__(self) -> None:
        pass

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        return '{"verdict": "safe", "category": null, "reason": "fake judge: always safe"}'


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


@pytest.fixture(autouse=True)
def _fake_embedding_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route rag_backend.embedding_model.client.embedding_client to the deterministic,
    no-network fake — otherwise every test that touches indexing or retrieval (most
    of the suite, since seed() runs on every app startup) would try to reach a
    nonexistent embedding-model container.
    """
    monkeypatch.setattr(
        embedding_model_client, "embedding_client", fake_embedding_client.EmbeddingClient()
    )


@pytest.fixture(autouse=True)
def _isolated_pipeline_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep per-request pipeline log files out of the real backend/pipeline-logs/."""
    monkeypatch.setattr(settings, "pipeline_log_dir", tmp_path / "pipeline-logs")


@pytest.fixture(autouse=True)
def _fake_guardrail_judge_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route rag_backend.guardrails.judge_client.guardrail_judge_client to a fake that
    always reports "safe" with no network call — otherwise every test exercising the
    retrieval pipeline would try to reach a nonexistent judge LLM, since guardrails are
    enabled by default. Guardrail-specific tests override this per-test.
    """
    monkeypatch.setattr(judge_client, "guardrail_judge_client", FakeGuardrailJudgeClient())


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(settings, "input_dir", tmp_path)
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
