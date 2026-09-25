from __future__ import annotations

from typing import Any

import httpx

from rag_backend.config import settings
from rag_backend.exceptions import RerankerModelError


class RerankerClient:
    """Thin client for the reranker-model container's text-embeddings-inference /rerank
    endpoint, serving a cross-encoder (cross-encoder/ms-marco-MiniLM-L-6-v2 by default).

    A cross-encoder reads the question and a passage together and outputs one relevance
    score, unlike the bi-encoder embedding model, which embeds each side separately.
    That makes it too slow to run over the whole corpus but accurate enough to reorder
    the few dozen candidates hybrid search already found.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url or settings.reranker_base_url
        self._model_name = model_name or settings.reranker_model_name
        self._transport = transport

    @property
    def model_name(self) -> str:
        return self._model_name

    async def score(self, query: str, texts: list[str]) -> list[float]:
        """Return one relevance score in [0, 1] per text, in the same order as texts.

        raw_scores=False makes TEI apply a sigmoid to the cross-encoder's logit, so scores
        are comparable across requests. truncate=True cuts over-long passages to the
        model's 512-token window instead of failing the request.
        """
        if not texts:
            return []
        batch_size = max(1, settings.reranker_batch_size)
        timeout = httpx.Timeout(settings.reranker_request_timeout_seconds)
        scores: list[float] = []
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as http_client:
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                scores.extend(await self._score_batch(http_client, query, batch))
        return scores

    async def _score_batch(
        self, http_client: httpx.AsyncClient, query: str, batch: list[str]
    ) -> list[float]:
        payload = {"query": query, "texts": batch, "raw_scores": False, "truncate": True}
        try:
            response = await http_client.post(f"{self._base_url}/rerank", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RerankerModelError(
                f"Rerank request failed for {len(batch)} texts: "
                f"{type(error).__name__} {error}".rstrip()
            ) from error
        return _scores_in_input_order(response.json(), len(batch))


def _scores_in_input_order(results: Any, expected_count: int) -> list[float]:
    """TEI returns [{"index": i, "score": s}, ...] sorted by score; put them back in the
    order the texts were sent."""
    scores: list[float | None] = [None] * expected_count
    try:
        for item in results:
            scores[int(item["index"])] = float(item["score"])
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise RerankerModelError(f"Malformed rerank response: {results!r:.200}") from error
    if any(score is None for score in scores):
        raise RerankerModelError(
            f"Rerank response scored {sum(s is not None for s in scores)} of "
            f"{expected_count} texts"
        )
    return [score for score in scores if score is not None]


reranker_client = RerankerClient()
