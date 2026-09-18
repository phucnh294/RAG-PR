from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from rag_backend.config import settings


class LlmClient:
    """Thin client for the dedicated llm-model Ollama container's /api/chat endpoint."""

    def __init__(self, base_url: str | None = None, model_name: str | None = None) -> None:
        self._base_url = base_url or settings.llm_base_url
        self._model_name = model_name or settings.llm_model_name

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield response content chunks as they arrive from Ollama's streaming chat API."""
        payload = {"model": self._model_name, "messages": messages, "stream": True}
        timeout = httpx.Timeout(settings.llm_request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            async with http_client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break


llm_client = LlmClient()
