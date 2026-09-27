from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

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
        google_model_name: str | None = None,
    ) -> None:
        self._base_url = base_url or settings.llm_base_url
        self._model_name = model_name or settings.llm_model_name
        self._provider = provider or settings.llm_provider
        self._google_api_key = google_api_key or settings.google_api_key
        self._google_model_name = google_model_name or settings.google_model_name
        self._timeout_seconds = request_timeout_seconds or settings.llm_request_timeout_seconds
        self._transport = transport

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model_name(self) -> str:
        """The model this client actually calls (the Gemini model when provider=google)."""
        return self._google_model_name if self._provider == "google" else self._model_name

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | str | None = None,
        options: dict[str, Any] | None = None,
        fail_on_truncation: bool = False,
    ) -> AsyncIterator[str]:
        """Yield response content chunks as they arrive from the configured LLM provider.

        A message may carry "images": a list of base64-encoded PNGs (vision models only).
        response_format asks for JSON output: "json", or a JSON schema that constrains
        generation (Ollama "format", Gemini "responseJsonSchema"). options are Ollama model
        options such as {"num_ctx": 8192, "temperature": 0}; Gemini maps temperature and
        ignores the rest (num_predict is NOT mapped to maxOutputTokens: Gemini thinking
        models spend that budget on thinking and cut the answer short).
        fail_on_truncation raises LlmClientError when the answer stopped at a length limit
        (Ollama done_reason "length", Gemini finishReason "MAX_TOKENS") instead of silently
        returning the cut-off text — for callers that parse the whole answer (agents).

        Raises LlmClientError for any transport/HTTP failure (provider down, 503, timeout),
        so callers handle one exception type and never see the request URL.
        """
        stream = (
            self._stream_chat_google(messages, response_format, options, fail_on_truncation)
            if self._provider == "google"
            else self._stream_chat_ollama(messages, response_format, options, fail_on_truncation)
        )
        try:
            async for content in stream:
                yield content
        except httpx.HTTPError as error:
            raise LlmClientError(
                f"{self._provider} request failed: {_describe_http_error(error)}"
            ) from error

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | str | None = None,
        options: dict[str, Any] | None = None,
        fail_on_truncation: bool = False,
    ) -> str:
        """Collect stream_chat into a single string for non-streaming callers (e.g. guardrail judges)."""
        chunks = [
            content
            async for content in self.stream_chat(
                messages,
                response_format=response_format,
                options=options,
                fail_on_truncation=fail_on_truncation,
            )
        ]
        return "".join(chunks)

    async def _stream_chat_ollama(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | str | None = None,
        options: dict[str, Any] | None = None,
        fail_on_truncation: bool = False,
    ) -> AsyncIterator[str]:
        """Yield response content chunks from Ollama's streaming /api/chat endpoint."""
        payload: dict[str, Any] = {"model": self._model_name, "messages": messages, "stream": True}
        if response_format is not None:
            payload["format"] = response_format
        if options:
            payload["options"] = options
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
                    if fail_on_truncation and chunk.get("done_reason") == "length":
                        raise LlmClientError(
                            "ollama response truncated: hit the token limit (done_reason=length)"
                        )
                    break

    async def _stream_chat_google(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | str | None = None,
        options: dict[str, Any] | None = None,
        fail_on_truncation: bool = False,
    ) -> AsyncIterator[str]:
        """Yield response content chunks from Gemini's streaming generateContent endpoint."""
        if not self._google_api_key:
            raise LlmClientError("GOOGLE_API_KEY is not set; required when LLM_PROVIDER=google.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._google_model_name}:streamGenerateContent"
        )
        payload: dict[str, Any] = {
            "contents": [
                {"role": _GOOGLE_ROLE_MAP.get(m["role"], "user"), "parts": _google_parts(m)}
                for m in messages
            ]
        }
        generation_config = _google_generation_config(response_format, options)
        if generation_config:
            payload["generationConfig"] = generation_config
        timeout = httpx.Timeout(self._timeout_seconds)
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
            finish_reason = None
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = json.loads(line.removeprefix("data: "))
                for candidate in chunk.get("candidates", []):
                    finish_reason = candidate.get("finishReason", finish_reason)
                    for part in candidate.get("content", {}).get("parts", []):
                        text = part.get("text", "")
                        if text:
                            yield text
            if fail_on_truncation and finish_reason == "MAX_TOKENS":
                raise LlmClientError("google response truncated: finishReason=MAX_TOKENS")


def _google_generation_config(
    response_format: dict[str, Any] | str | None, options: dict[str, Any] | None
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if response_format is not None:
        config["responseMimeType"] = "application/json"
    if isinstance(response_format, dict):
        config["responseJsonSchema"] = response_format
    if options and "temperature" in options:
        config["temperature"] = options["temperature"]
    return config


def _google_parts(message: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"text": message["content"]}]
    for image in message.get("images", []):
        parts.append({"inline_data": {"mime_type": "image/png", "data": image}})
    return parts


def _describe_http_error(error: httpx.HTTPError) -> str:
    """A log-safe summary: status or error type only, never the request URL."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code} {error.response.reason_phrase}".rstrip()
    return type(error).__name__


llm_client = LlmClient()
