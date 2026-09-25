from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from rag_backend.config import settings

_GOOGLE_ROLE_MAP = {"assistant": "model", "system": "user", "user": "user"}


class LlmClientError(Exception):
    """Raised when the configured LLM provider is misconfigured or returns a bad response."""


class LlmClient:
    """Client for the configured LLM provider: the local Ollama llm-model container, or Google's Gemini API."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        provider: str | None = None,
        google_api_key: str | None = None,
        request_timeout_seconds: float | None = None,
    ) -> None:
        self._base_url = base_url or settings.llm_base_url
        self._model_name = model_name or settings.llm_model_name
        self._provider = provider or settings.llm_provider
        self._google_api_key = google_api_key or settings.google_api_key
        self._timeout_seconds = request_timeout_seconds or settings.llm_request_timeout_seconds

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield response content chunks as they arrive from the configured LLM provider."""
        if self._provider == "google":
            async for content in self._stream_chat_google(messages):
                yield content
        else:
            async for content in self._stream_chat_ollama(messages):
                yield content

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        """Collect stream_chat into a single string for non-streaming callers (e.g. guardrail judges)."""
        try:
            chunks = [content async for content in self.stream_chat(messages)]
        except httpx.HTTPError as error:
            raise LlmClientError(f"LLM provider request failed: {error}") from error
        return "".join(chunks)

    async def _stream_chat_ollama(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield response content chunks from Ollama's streaming /api/chat endpoint."""
        payload = {"model": self._model_name, "messages": messages, "stream": True}
        timeout = httpx.Timeout(self._timeout_seconds)
        async with (
            httpx.AsyncClient(timeout=timeout) as http_client,
            http_client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response,
        ):
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

    async def _stream_chat_google(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield response content chunks from Gemini's streaming generateContent endpoint."""
        if not self._google_api_key:
            raise LlmClientError("GOOGLE_API_KEY is not set; required when LLM_PROVIDER=google.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.google_model_name}:streamGenerateContent"
        )
        payload = {
            "contents": [
                {"role": _GOOGLE_ROLE_MAP.get(m["role"], "user"), "parts": [{"text": m["content"]}]}
                for m in messages
            ]
        }
        timeout = httpx.Timeout(settings.llm_request_timeout_seconds)
        async with (
            httpx.AsyncClient(timeout=timeout) as http_client,
            http_client.stream(
                "POST",
                url,
                params={"key": self._google_api_key, "alt": "sse"},
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = json.loads(line.removeprefix("data: "))
                for candidate in chunk.get("candidates", []):
                    for part in candidate.get("content", {}).get("parts", []):
                        text = part.get("text", "")
                        if text:
                            yield text


llm_client = LlmClient()
