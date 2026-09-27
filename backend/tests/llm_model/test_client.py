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


async def test_ollama_payload_carries_images_format_and_options() -> None:
    import json

    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text='{"message": {"content": "{}"}, "done": true}\n')

    client = LlmClient(
        provider="ollama", base_url="http://vision", transport=httpx.MockTransport(handler)
    )
    schema = {"type": "object"}

    await client.complete_chat(
        [{"role": "user", "content": "describe", "images": ["aGVsbG8="]}],
        response_format=schema,
        options={"num_ctx": 8192},
    )

    body = bodies[0]
    assert body["messages"] == [{"role": "user", "content": "describe", "images": ["aGVsbG8="]}]
    assert body["format"] == schema
    assert body["options"] == {"num_ctx": 8192}


async def test_ollama_payload_unchanged_for_plain_text_callers() -> None:
    import json

    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text='{"message": {"content": "hi"}, "done": true}\n')

    client = LlmClient(
        provider="ollama", base_url="http://llm", transport=httpx.MockTransport(handler)
    )

    await client.complete_chat([{"role": "user", "content": "hello"}])

    assert set(bodies[0]) == {"model", "messages", "stream"}


async def test_google_payload_sends_images_as_inline_data_and_json_mime_type() -> None:
    import json

    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        body = 'data: {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}\n\n'
        return httpx.Response(200, text=body)

    client = LlmClient(
        provider="google",
        google_api_key=_SECRET,
        google_model_name="gemini-vision",
        transport=httpx.MockTransport(handler),
    )

    schema = {"type": "object", "properties": {"a": {"type": "string"}}}

    await client.complete_chat(
        [{"role": "user", "content": "describe", "images": ["aGVsbG8="]}], response_format=schema
    )

    body = bodies[0]
    assert body["contents"] == [
        {
            "role": "user",
            "parts": [
                {"text": "describe"},
                {"inline_data": {"mime_type": "image/png", "data": "aGVsbG8="}},
            ],
        }
    ]
    assert body["generationConfig"] == {
        "responseMimeType": "application/json",
        "responseJsonSchema": schema,
    }
    assert client.model_name == "gemini-vision"


async def test_google_maps_temperature_but_not_num_predict_into_generation_config() -> None:
    import json

    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        body = 'data: {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}\n\n'
        return httpx.Response(200, text=body)

    client = LlmClient(
        provider="google", google_api_key=_SECRET, transport=httpx.MockTransport(handler)
    )

    await client.complete_chat(
        [{"role": "user", "content": "x"}],
        response_format="json",
        options={"num_ctx": 8192, "temperature": 0.0, "num_predict": 3072},
    )

    # No maxOutputTokens: Gemini thinking models count thinking against it and the
    # answer comes back cut off mid-JSON.
    assert bodies[0]["generationConfig"] == {
        "responseMimeType": "application/json",
        "temperature": 0.0,
    }


async def test_truncated_google_answer_raises_only_when_asked() -> None:
    body = (
        'data: {"candidates": [{"content": {"parts": [{"text": "{\\"a\\": "}]}}]}\n\n'
        'data: {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}\n\n'
    )
    client = LlmClient(
        provider="google",
        google_api_key=_SECRET,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)),
    )
    messages = [{"role": "user", "content": "x"}]

    assert await client.complete_chat(messages) == '{"a": '
    with pytest.raises(LlmClientError, match="MAX_TOKENS"):
        await client.complete_chat(messages, fail_on_truncation=True)


async def test_truncated_ollama_answer_raises_only_when_asked() -> None:
    body = (
        '{"message": {"content": "{\\"a\\": "}, "done": false}\n'
        '{"message": {"content": ""}, "done": true, "done_reason": "length"}\n'
    )
    client = LlmClient(
        provider="ollama",
        base_url="http://vision",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)),
    )
    messages = [{"role": "user", "content": "x"}]

    assert await client.complete_chat(messages) == '{"a": '
    with pytest.raises(LlmClientError, match="truncated"):
        await client.complete_chat(messages, fail_on_truncation=True)
