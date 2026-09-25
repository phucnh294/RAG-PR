from __future__ import annotations

import json

import httpx
import pytest

from rag_backend.config import settings
from rag_backend.embedding_model.client import EmbeddingClient
from rag_backend.exceptions import EmbeddingModelError


async def test_embed_texts_sends_batches_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "embedding_batch_size", 2)
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)["input"]
        batches.append(batch)
        return httpx.Response(200, json={"embeddings": [[float(text)] for text in batch]})

    client = EmbeddingClient(base_url="http://embed", transport=httpx.MockTransport(handler))
    embeddings = await client.embed_texts(["1", "2", "3", "4", "5"])

    assert batches == [["1", "2"], ["3", "4"], ["5"]]
    assert embeddings == [[1.0], [2.0], [3.0], [4.0], [5.0]]


async def test_embed_texts_wraps_timeout_in_embedding_model_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = EmbeddingClient(base_url="http://embed", transport=httpx.MockTransport(handler))

    with pytest.raises(EmbeddingModelError, match="ReadTimeout"):
        await client.embed_texts(["hello"])


async def test_embed_texts_wraps_http_error_status_in_embedding_model_error() -> None:
    client = EmbeddingClient(
        base_url="http://embed",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )

    with pytest.raises(EmbeddingModelError):
        await client.embed_texts(["hello"])
