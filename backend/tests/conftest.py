from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_backend.auth import repository as auth_repository
from rag_backend.auth import seed as auth_seed
from rag_backend.auth import service as auth_service
from rag_backend.auth.dependencies import USER_ID_HEADER
from rag_backend.auth.models import ADMIN_ROLE, CurrentUser
from rag_backend.config import settings
from rag_backend.db import authz_schema, postgres_store
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
    "get_document_unscoped",
    "find_existing",
    "add_document",
    "update_document",
    "update_document_metadata",
    "delete_document",
    "add_chunks",
    "get_chunks",
    "all_chunks",
    "search_similar_chunks",
    "search_fulltext_chunks",
    "ensure_fulltext_index",
    "seed",
)

_AUTH_REPOSITORY_FUNCTIONS = (
    "ensure_role",
    "ensure_classification",
    "list_roles",
    "list_classifications",
    "get_user",
    "get_user_by_username",
    "list_users",
    "create_user",
    "upsert_user",
    "set_user_role",
    "set_user_active",
    "get_allowed_classifications",
    "list_access",
    "grant_access",
    "mark_grant_seeded",
    "revoke_access",
)


async def _noop_pool_lifecycle() -> None:
    return None


async def _noop_finalize_document_ownership(admin_user_id: str, default: str) -> None:
    return None


@pytest.fixture(autouse=True)
def _fake_postgres_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route every rag_backend.db.postgres_store and rag_backend.auth.repository call to
    the in-memory dummy_store, and make the schema/pool startup steps no-ops.

    Pipeline/route code always calls "postgres_store.xxx(...)" / "repository.xxx(...)" —
    this makes tests exercise that exact code path without a live Postgres connection.
    """
    for name in _STORE_FUNCTIONS:
        monkeypatch.setattr(postgres_store, name, getattr(dummy_store, name))
    for name in _AUTH_REPOSITORY_FUNCTIONS:
        monkeypatch.setattr(auth_repository, name, getattr(dummy_store, name))
    monkeypatch.setattr(db_session, "init_pool", _noop_pool_lifecycle)
    monkeypatch.setattr(db_session, "close_pool", _noop_pool_lifecycle)
    monkeypatch.setattr(authz_schema, "ensure_authorization_schema", _noop_pool_lifecycle)
    monkeypatch.setattr(
        authz_schema, "finalize_document_ownership", _noop_finalize_document_ownership
    )
    dummy_store.reset()


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


def _usernames_by_role() -> dict[str, str]:
    return {
        role: settings.admin_username if role == ADMIN_ROLE else auth_seed.demo_username(role)
        for role in settings.auth_roles
    }


def _user_id(username: str) -> str:
    return next(user.id for user in dummy_store._users.values() if user.username == username)


@pytest.fixture
async def auth_users() -> dict[str, CurrentUser]:
    """Seed roles/classifications/admin/demo users (as app startup does) and return one
    resolved CurrentUser per role — for tests that call pipeline code directly."""
    await auth_seed.bootstrap_authorization()
    users: dict[str, CurrentUser] = {}
    for role, username in _usernames_by_role().items():
        record = await auth_repository.get_user_by_username(username)
        assert record is not None
        users[role] = await auth_service.build_current_user(record)
    return users


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """App client that authenticates as the seeded admin by default; override per request
    with headers=role_headers["user"] etc."""
    monkeypatch.setattr(settings, "input_dir", tmp_path)
    app = create_app()
    with TestClient(app) as test_client:
        test_client.headers[USER_ID_HEADER] = _user_id(settings.admin_username)
        yield test_client


@pytest.fixture
def role_headers(client: TestClient) -> dict[str, dict[str, str]]:
    """X-User-Id headers for the seeded user of each role (requires the app started)."""
    return {
        role: {USER_ID_HEADER: _user_id(username)}
        for role, username in _usernames_by_role().items()
    }
