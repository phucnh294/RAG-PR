from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from rag_backend.llm_model.client import LlmClient


class FakeLlmClient(LlmClient):
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        for token in self._tokens:
            yield token


def test_chat_streams_llm_tokens_then_citations(client: TestClient, monkeypatch) -> None:
    fake_client = FakeLlmClient(tokens=["Employees ", "get ", "20 ", "days."])
    monkeypatch.setattr("rag_backend.api.routes_chat.llm_client", fake_client)

    response = client.post("/chat", json={"message": "how many days of leave do I get?"})

    assert response.status_code == 200
    body = response.text
    answer_part, _, citations_part = body.partition("\x00CITATIONS:")
    assert answer_part == "Employees get 20 days."
    assert "employee_handbook.md" in citations_part
