from __future__ import annotations

from fastapi.testclient import TestClient


def test_upload_then_list_returns_document(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("note.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["already_exists"] is False

    listed = client.get("/documents").json()
    assert any(doc["filename"] == "note.txt" for doc in listed)


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
