from __future__ import annotations

from collections.abc import AsyncIterator

from rag_backend.llm_model import client as llm_model_client


async def call_llm_model(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """Stream the LLM's response for the given messages.

    Looks up llm_model_client.llm_client on every call (rather than binding it as a
    default argument) so tests can monkeypatch the module-level singleton.
    """
    async for token in llm_model_client.llm_client.stream_chat(messages):
        yield token
