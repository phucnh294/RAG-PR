from __future__ import annotations

from fastapi.testclient import TestClient

from rag_backend.auth.dependencies import USER_ID_HEADER
from rag_backend.main import REQUEST_ID_HEADER
from rag_backend.storage import dummy_store


def test_protected_endpoint_without_user_header_returns_401(client: TestClient) -> None:
    client.headers.pop(USER_ID_HEADER)

    response = client.get("/documents")

    assert response.status_code == 401


def test_unknown_user_id_returns_401(client: TestClient) -> None:
    response = client.get("/documents", headers={USER_ID_HEADER: "not-a-real-user"})

    assert response.status_code == 401


async def test_inactive_user_returns_403(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    staff_id = role_headers["staff"][USER_ID_HEADER]
    await dummy_store.set_user_active(staff_id, False)

    response = client.get("/documents", headers=role_headers["staff"])

    assert response.status_code == 403


def test_me_reports_role_and_allowed_classifications_from_the_database(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    body = client.get("/auth/me", headers=role_headers["staff"]).json()

    assert body["role"] == "staff"
    assert body["allowed_classifications"] == ["public", "internal"]
    assert body["is_admin"] is False


def test_health_and_demo_users_need_no_identity(client: TestClient) -> None:
    client.headers.pop(USER_ID_HEADER)

    assert client.get("/health").status_code == 200
    demo_users = client.get("/auth/demo-users").json()
    assert {user["role"] for user in demo_users} == {"user", "staff", "manager", "admin"}


def test_every_response_echoes_the_request_id(client: TestClient) -> None:
    response = client.get("/documents", headers={REQUEST_ID_HEADER: "trace-123"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-123"
    assert client.get("/documents").headers[REQUEST_ID_HEADER]
