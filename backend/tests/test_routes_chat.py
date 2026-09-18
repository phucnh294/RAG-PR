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


def test_chat_streams_llm_tokens_then_citations(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = FakeLlmClient(tokens=["Employees ", "get ", "20 ", "days."])
    monkeypatch.setattr("rag_backend.llm_model.client.llm_client", fake_client)

    # Exact wording of the seeded employee_handbook.md content guarantees this
    # chunk gets the highest (near-1.0) cosine similarity under the stub embedding.
    question = "All employees are entitled to 20 days of paid annual leave per calendar year."
    response = client.post("/chat", json={"message": question})

    assert response.status_code == 200
    body = response.text
    answer_part, _, citations_part = body.partition("\x00CITATIONS:")
    assert answer_part == "Employees get 20 days."
    assert "employee_handbook.md" in citations_part


def test_chat_says_it_does_not_know_when_nothing_is_similar_enough(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = FakeLlmClient(tokens=["I don't know."])
    monkeypatch.setattr("rag_backend.llm_model.client.llm_client", fake_client)

    response = client.post(
        "/chat", json={"message": "zzz qqq xxx completely unrelated gibberish yyy www"}
    )

    body = response.text
    _, _, citations_part = body.partition("\x00CITATIONS:")
    assert citations_part == "[]"
