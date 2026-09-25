from __future__ import annotations

import httpx
import pytest

from rag_backend.llm_model.client import LlmClient, LlmClientError

_SECRET = "test-secret-key"


def _google_client(handler: httpx.MockTransport) -> LlmClient:
    return LlmClient(provider="google", google_api_key=_SECRET, transport=handler)


async def test_google_request_sends_api_key_in_header_not_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = 'data: {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}\n\n'
        return httpx.Response(200, text=body)

    answer = await _google_client(httpx.MockTransport(handler)).complete_chat(
        [{"role": "user", "content": "hello"}]
    )

    assert answer == "hi"
    assert seen[0].headers["x-goog-api-key"] == _SECRET
    assert _SECRET not in str(seen[0].url)


async def test_provider_error_becomes_llm_client_error_without_url_or_key() -> None:
    client = _google_client(httpx.MockTransport(lambda request: httpx.Response(503)))

    with pytest.raises(LlmClientError) as raised:
        await client.complete_chat([{"role": "user", "content": "hello"}])

    message = str(raised.value)
    assert "503" in message
    assert _SECRET not in message
    assert "googleapis.com" not in message


async def test_stream_chat_wraps_transport_errors_too() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    client = LlmClient(
        provider="ollama", base_url="http://llm", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(LlmClientError, match="ConnectError"):
        async for _ in client.stream_chat([{"role": "user", "content": "hello"}]):
            pass
