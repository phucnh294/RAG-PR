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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url or settings.llm_base_url
        self._model_name = model_name or settings.llm_model_name
        self._provider = provider or settings.llm_provider
        self._google_api_key = google_api_key or settings.google_api_key
        self._timeout_seconds = request_timeout_seconds or settings.llm_request_timeout_seconds
        self._transport = transport

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield response content chunks as they arrive from the configured LLM provider.

        Raises LlmClientError for any transport/HTTP failure (provider down, 503, timeout),
        so callers handle one exception type and never see the request URL.
        """
        stream = (
            self._stream_chat_google(messages)
            if self._provider == "google"
            else self._stream_chat_ollama(messages)
        )
        try:
            async for content in stream:
                yield content
        except httpx.HTTPError as error:
            raise LlmClientError(
                f"{self._provider} request failed: {_describe_http_error(error)}"
            ) from error

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        """Collect stream_chat into a single string for non-streaming callers (e.g. guardrail judges)."""
        chunks = [content async for content in self.stream_chat(messages)]
        return "".join(chunks)

    async def _stream_chat_ollama(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield response content chunks from Ollama's streaming /api/chat endpoint."""
        payload = {"model": self._model_name, "messages": messages, "stream": True}
        timeout = httpx.Timeout(self._timeout_seconds)
        async with (
            httpx.AsyncClient(timeout=timeout, transport=self._transport) as http_client,
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
            httpx.AsyncClient(timeout=timeout, transport=self._transport) as http_client,
            http_client.stream(
                "POST",
                url,
                # Key in a header, not the query string: httpx puts the full URL into
                # error messages, which would write the key into logs.
                params={"alt": "sse"},
                headers={"x-goog-api-key": self._google_api_key},
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


def _describe_http_error(error: httpx.HTTPError) -> str:
    """A log-safe summary: status or error type only, never the request URL."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code} {error.response.reason_phrase}".rstrip()
    return type(error).__name__


llm_client = LlmClient()
