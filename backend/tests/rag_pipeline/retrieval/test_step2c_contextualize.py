from __future__ import annotations

import pytest

from rag_backend.config import settings
from rag_backend.conversations.models import Turn
from rag_backend.llm_model.client import LlmClient, LlmClientError
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import NormalizedQuery
from rag_backend.rag_pipeline.retrieval.step2c_contextualize import contextualize

_HISTORY = [Turn(question="What is the annual leave policy?", answer="20 days per year.")]


class FakeRewriteClient(LlmClient):
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.reply


class FailingRewriteClient(LlmClient):
    def __init__(self) -> None:
        pass

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        raise LlmClientError("ollama request failed: timeout")


def _use_llm(monkeypatch: pytest.MonkeyPatch, client: LlmClient) -> None:
    monkeypatch.setattr("rag_backend.llm_model.client.llm_client", client)


async def test_contextualize_rewrites_a_follow_up_using_the_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRewriteClient('Standalone question: "Can unused annual leave be carried over?"')
    _use_llm(monkeypatch, fake)

    result = await contextualize(NormalizedQuery(text="can it be carried over?"), _HISTORY)

    assert result.rewritten is True
    assert result.query.text == "Can unused annual leave be carried over?"
    prompt = fake.calls[0][1]["content"]
    assert "User: What is the annual leave policy?" in prompt
    assert "Follow-up question: can it be carried over?" in prompt


async def test_contextualize_passes_through_without_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRewriteClient("should not be used")
    _use_llm(monkeypatch, fake)
    query = NormalizedQuery(text="what is the leave policy?", document_ids=["d1"])

    result = await contextualize(query, [])

    assert result.query is query
    assert result.rewritten is False
    assert fake.calls == []


async def test_contextualize_passes_through_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRewriteClient("should not be used")
    _use_llm(monkeypatch, fake)
    monkeypatch.setattr(settings, "contextualize_enabled", False)

    result = await contextualize(NormalizedQuery(text="and for managers?"), _HISTORY)

    assert result.query.text == "and for managers?"
    assert fake.calls == []


async def test_contextualize_falls_back_to_the_question_when_the_llm_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_llm(monkeypatch, FailingRewriteClient())

    result = await contextualize(NormalizedQuery(text="and for managers?"), _HISTORY)

    assert result.query.text == "and for managers?"
    assert result.rewritten is False
    assert result.error is not None and "timeout" in result.error


async def test_contextualize_falls_back_on_an_empty_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_llm(monkeypatch, FakeRewriteClient("   \n  "))

    result = await contextualize(NormalizedQuery(text="and for managers?"), _HISTORY)

    assert result.query.text == "and for managers?"
    assert result.error == "empty rewrite"
