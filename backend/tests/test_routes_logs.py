from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from rag_backend.llm_model.client import LlmClient


class FakeLlmClient(LlmClient):
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        for token in self._tokens:
            yield token


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rag_backend.llm_model.client.llm_client", FakeLlmClient(tokens=["ok"]))


def test_list_logs_returns_entries_from_indexing_and_retrieval(client: TestClient) -> None:
    # The client fixture's app startup seeds 3 documents through the real indexing
    # pipeline, so indexing logs already exist without any extra setup here.
    upload = client.post(
        "/documents", files={"file": ("note.txt", b"hello there", "text/plain")}
    ).json()

    client.post("/chat", json={"message": "hello there"})

    logs = client.get("/logs").json()
    pipelines = {entry["pipeline"] for entry in logs}
    assert "indexing" in pipelines
    assert "retrieval" in pipelines
    assert any(upload["document"]["filename"] in entry["summary"] for entry in logs)


def test_list_logs_filters_by_pipeline(client: TestClient) -> None:
    client.post("/chat", json={"message": "hello there"})

    logs = client.get("/logs", params={"pipeline": "retrieval"}).json()
    assert len(logs) > 0
    assert all(entry["pipeline"] == "retrieval" for entry in logs)


def test_list_logs_rejects_unknown_pipeline(client: TestClient) -> None:
    response = client.get("/logs", params={"pipeline": "bogus"})
    assert response.status_code == 400


def test_get_log_returns_full_record(client: TestClient) -> None:
    logs = client.get("/logs", params={"pipeline": "indexing"}).json()
    log_id = logs[0]["id"]

    response = client.get(f"/logs/indexing/{log_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == log_id
    assert body["pipeline"] == "indexing"
    assert "status" in body["record"]


def test_get_log_rejects_path_traversal_attempt(client: TestClient) -> None:
    response = client.get("/logs/indexing/..%2F..%2Fsecret")
    assert response.status_code == 404


def test_get_log_returns_404_for_missing_log(client: TestClient) -> None:
    response = client.get("/logs/indexing/20260101T000000000000_does-not-exist")
    assert response.status_code == 404
