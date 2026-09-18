from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from rag_backend.llm_model.client import LlmClient
from rag_backend.rag_pipeline.retrieval.step9_call_llm_model import call_llm_model


class FakeLlmClient(LlmClient):
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        for token in self._tokens:
            yield token


async def test_call_llm_model_streams_tokens_from_the_patched_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rag_backend.llm_model.client.llm_client", FakeLlmClient(tokens=["a", "b", "c"])
    )

    tokens = [token async for token in call_llm_model([{"role": "user", "content": "hi"}])]

    assert tokens == ["a", "b", "c"]
