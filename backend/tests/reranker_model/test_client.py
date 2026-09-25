from __future__ import annotations

import json

import httpx
import pytest

from rag_backend.config import settings
from rag_backend.exceptions import RerankerModelError
from rag_backend.reranker_model.client import RerankerClient


async def test_score_sends_tei_rerank_request_and_returns_scores_in_input_order() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append({"path": request.url.path, **body})
        # TEI sorts results by score, not by input position.
        return httpx.Response(200, json=[{"index": 1, "score": 0.9}, {"index": 0, "score": 0.2}])

    client = RerankerClient(base_url="http://rerank", transport=httpx.MockTransport(handler))
    scores = await client.score("question", ["first", "second"])

    assert scores == [0.2, 0.9]
    assert requests == [
        {
            "path": "/rerank",
            "query": "question",
            "texts": ["first", "second"],
            "raw_scores": False,
            "truncate": True,
        }
    ]


async def test_score_splits_requests_into_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "reranker_batch_size", 2)
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["texts"]
        batches.append(texts)
        return httpx.Response(
            200, json=[{"index": i, "score": float(text)} for i, text in enumerate(texts)]
        )

    client = RerankerClient(base_url="http://rerank", transport=httpx.MockTransport(handler))

    assert await client.score("q", ["1", "2", "3"]) == [1.0, 2.0, 3.0]
    assert batches == [["1", "2"], ["3"]]


async def test_score_with_no_texts_makes_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    client = RerankerClient(base_url="http://rerank", transport=httpx.MockTransport(handler))

    assert await client.score("q", []) == []


async def test_score_wraps_timeout_in_reranker_model_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = RerankerClient(base_url="http://rerank", transport=httpx.MockTransport(handler))

    with pytest.raises(RerankerModelError, match="ReadTimeout"):
        await client.score("q", ["text"])


async def test_score_rejects_a_response_missing_a_text() -> None:
    client = RerankerClient(
        base_url="http://rerank",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=[{"index": 0, "score": 0.5}])
        ),
    )

    with pytest.raises(RerankerModelError, match="scored 1 of 2"):
        await client.score("q", ["a", "b"])
