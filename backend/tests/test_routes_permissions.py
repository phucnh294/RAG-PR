"""End-to-end authorization through the HTTP API: what each role can retrieve through
chat, which pipeline logs it can read, and the admin-only management endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from rag_backend.auth.dependencies import USER_ID_HEADER
from rag_backend.llm_model.client import LlmClient
from rag_backend.rag_pipeline.retrieval.step10_response import CITATIONS_MARKER

_SECRET = "Project Falcon merger closes on the fourteenth of March at noon."


class _FakeLlmClient(LlmClient):
    def __init__(self) -> None:
        pass

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "ok"


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rag_backend.llm_model.client.llm_client", _FakeLlmClient())


def _ask(client: TestClient, headers: dict[str, str], question: str) -> dict[str, object]:
    body = client.post("/chat", json={"message": question}, headers=headers).text
    _, _, payload = body.partition(CITATIONS_MARKER)
    return dict(json.loads(payload))


def _upload_secret(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/documents",
        files={"file": ("falcon.txt", _SECRET.encode(), "text/plain")},
        data={"classification": "confidential"},
        headers=headers,
    )
    return str(response.json()["document"]["id"])


def test_chat_never_cites_documents_above_the_callers_clearance(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    document_id = _upload_secret(client, role_headers["manager"])

    def _cited(role: str) -> set[str]:
        citations = _ask(client, role_headers[role], _SECRET)["citations"]
        assert isinstance(citations, list)
        return {citation["document_id"] for citation in citations}

    assert document_id in _cited("manager")
    assert document_id in _cited("admin")
    assert document_id not in _cited("staff")
    assert document_id not in _cited("user")


def test_revoking_a_grant_takes_effect_on_the_next_request(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    document_id = _upload_secret(client, role_headers["manager"])

    revoke = client.put(
        "/auth/access",
        json={"role": "manager", "classification": "confidential", "granted": False},
    )

    assert revoke.status_code == 200
    assert "confidential" not in revoke.json()["access"]["manager"]
    listed = client.get("/documents", headers=role_headers["manager"]).json()
    assert document_id not in {doc["id"] for doc in listed}


def test_retrieval_log_records_who_asked_and_the_search_state(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    _ask(client, role_headers["staff"], "annual leave")

    logs = client.get("/logs", params={"pipeline": "retrieval"}).json()
    record = client.get(f"/logs/retrieval/{logs[0]['id']}").json()["record"]

    assert record["username"] == "demo_staff"
    assert record["role"] == "staff"
    assert record["state"]["allowed_classifications"] == ["internal", "public"]
    assert record["state"]["search_mode"] == "hybrid"
    assert record["steps"]["4_similarity_search"]["input"]["role"] == "staff"


def test_non_admins_only_see_their_own_logs(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    _ask(client, role_headers["staff"], "staff question")
    _ask(client, role_headers["user"], "user question")

    staff_logs = client.get("/logs", headers=role_headers["staff"]).json()
    admin_logs = client.get("/logs").json()

    assert [entry["summary"] for entry in staff_logs] == ["staff question"]
    assert {"staff question", "user question"} <= {entry["summary"] for entry in admin_logs}
    # Another user's log is a 404, not a 403: its existence is not confirmed.
    user_log = next(entry for entry in admin_logs if entry["summary"] == "user question")
    detail = client.get(f"/logs/retrieval/{user_log['id']}", headers=role_headers["staff"])
    assert detail.status_code == 404


def test_admin_endpoints_reject_non_admins(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    manager = role_headers["manager"]

    assert client.get("/auth/users", headers=manager).status_code == 403
    assert client.get("/auth/access", headers=manager).status_code == 403
    assert client.post("/eval/run", headers=manager).status_code == 403
    assert client.post("/auth/users", json={"username": "eve"}, headers=manager).status_code == 403


def test_admin_creates_a_user_and_assigns_a_role(client: TestClient) -> None:
    created = client.post("/auth/users", json={"username": "alice"})
    assert created.status_code == 201
    assert created.json()["role"] == "user"
    assert client.post("/auth/users", json={"username": "alice"}).status_code == 409

    alice_id = created.json()["id"]
    promoted = client.put(f"/auth/users/{alice_id}/role", json={"role": "manager"})
    assert promoted.json()["role"] == "manager"
    me = client.get("/auth/me", headers={USER_ID_HEADER: alice_id}).json()
    assert me["allowed_classifications"] == ["public", "internal", "confidential"]

    bad_role = client.put(f"/auth/users/{alice_id}/role", json={"role": "wizard"})
    assert bad_role.status_code == 422


def test_classifications_endpoint_drives_the_upload_form(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    user_view = client.get("/auth/classifications", headers=role_headers["user"]).json()
    staff_view = client.get("/auth/classifications", headers=role_headers["staff"]).json()

    assert user_view == {
        "allowed": ["public"],
        "default": "public",
        "all": ["public", "internal", "confidential", "restricted"],
    }
    assert staff_view["allowed"] == ["public", "internal"]
    assert staff_view["default"] == "internal"
