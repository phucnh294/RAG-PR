from __future__ import annotations

from fastapi.testclient import TestClient
from httpx import Response

from rag_backend.config import settings
from rag_backend.storage import dummy_store


def test_upload_then_list_returns_document(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("note.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["already_exists"] is False

    listed = client.get("/documents").json()
    assert any(doc["filename"] == "note.txt" for doc in listed)


async def test_upload_triggers_indexing_pipeline_to_completion(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("note.txt", b"hello world, this is indexed content", "text/plain")},
    )
    document_id = response.json()["document"]["id"]

    # TestClient runs FastAPI BackgroundTasks synchronously before returning,
    # so indexing has already completed by the time the response comes back.
    updated = await dummy_store.get_document_unscoped(document_id)
    assert updated is not None
    assert updated.status == "ready"
    assert len(await dummy_store.get_chunks(document_id)) > 0


def test_upload_duplicate_bytes_returns_existing_document(client: TestClient) -> None:
    files = {"file": ("note.txt", b"same bytes", "text/plain")}
    first = client.post("/documents", files=files).json()
    second = client.post("/documents", files=files).json()

    assert second["already_exists"] is True
    assert second["document"]["id"] == first["document"]["id"]


def test_upload_rejects_disallowed_mime_type(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("image.png", b"fake-bytes", "image/png")},
    )
    assert response.status_code == 415


def test_delete_removes_document(client: TestClient) -> None:
    uploaded = client.post(
        "/documents",
        files={"file": ("temp.txt", b"temp content", "text/plain")},
    ).json()
    document_id = uploaded["document"]["id"]

    delete_response = client.delete(f"/documents/{document_id}")
    assert delete_response.status_code == 204

    listed = client.get("/documents").json()
    assert all(doc["id"] != document_id for doc in listed)


def _upload(
    client: TestClient,
    headers: dict[str, str],
    content: bytes = b"shared bytes",
    filename: str = "note.txt",
    mime_type: str = "text/plain",
    **form: str,
) -> Response:
    return client.post(
        "/documents", files={"file": (filename, content, mime_type)}, data=form, headers=headers
    )


def test_upload_uses_default_classification_and_records_creator_and_tags(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    response = _upload(client, role_headers["staff"], tags="hr, policy ,hr")

    document = response.json()["document"]
    assert document["classification"] == settings.auth_default_classification
    assert document["created_by_username"] == "demo_staff"
    assert document["tags"] == ["hr", "policy"]
    assert document["can_delete"] is True


def test_upload_above_clearance_is_forbidden(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    response = _upload(client, role_headers["staff"], classification="confidential")

    assert response.status_code == 403


def test_upload_with_unknown_classification_is_rejected(client: TestClient) -> None:
    response = _upload(client, {}, classification="top-secret")

    assert response.status_code == 422


def test_upload_reads_classification_from_markdown_frontmatter(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    content = b"---\ntitle: Pay bands\nclassification: confidential\n---\n## Q1: What?\nA.\n"

    response = _upload(
        client, role_headers["manager"], content, filename="pay.md", mime_type="text/markdown"
    )

    assert response.json()["document"]["classification"] == "confidential"


def test_dedup_is_per_classification_hash_and_creator(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    first = _upload(client, role_headers["staff"]).json()
    same_again = _upload(client, role_headers["staff"]).json()
    other_classification = _upload(client, role_headers["staff"], classification="public").json()
    other_creator = _upload(client, role_headers["manager"]).json()

    assert same_again["already_exists"] is True
    assert same_again["document"]["id"] == first["document"]["id"]
    assert other_classification["already_exists"] is False
    assert other_creator["already_exists"] is False
    assert len({first["document"]["id"], other_classification["document"]["id"],
                other_creator["document"]["id"]}) == 3  # fmt: skip


def test_list_documents_only_shows_readable_classifications(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    secret = _upload(client, {}, b"secret", classification="confidential").json()["document"]

    def _visible(role: str) -> set[str]:
        return {doc["id"] for doc in client.get("/documents", headers=role_headers[role]).json()}

    assert secret["id"] in _visible("manager")
    assert secret["id"] in _visible("admin")
    assert secret["id"] not in _visible("staff")
    assert secret["id"] not in _visible("user")
    # Seed documents are public, so every role sees something.
    assert _visible("user")


def test_get_document_hides_unreadable_documents_as_404(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    secret = _upload(client, {}, b"secret", classification="restricted").json()["document"]

    assert client.get(f"/documents/{secret['id']}").status_code == 200
    assert client.get(
        f"/documents/{secret['id']}", headers=role_headers["manager"]
    ).status_code == (404)


def test_delete_rules_creator_or_admin(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    staff_doc = _upload(client, role_headers["staff"]).json()["document"]
    other_staff_doc = _upload(client, role_headers["staff"], b"other").json()["document"]
    secret = _upload(client, {}, b"secret", classification="restricted").json()["document"]

    # Visible but not theirs -> 403; not visible -> 404 (existence not confirmed).
    assert client.delete(f"/documents/{staff_doc['id']}", headers=role_headers["manager"]).status_code == 403  # fmt: skip
    assert client.delete(f"/documents/{secret['id']}", headers=role_headers["manager"]).status_code == 404  # fmt: skip
    # Creator and admin may delete.
    assert client.delete(f"/documents/{staff_doc['id']}", headers=role_headers["staff"]).status_code == 204  # fmt: skip
    assert client.delete(f"/documents/{other_staff_doc['id']}").status_code == 204
