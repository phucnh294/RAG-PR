from __future__ import annotations

import httpx

from rag_backend.config import settings
from rag_backend.exceptions import EmbeddingModelError


class EmbeddingClient:
    """Thin client for the dedicated embedding-model container's /api/embed endpoint.

    Mirrors llm_model/client.py's shape. Deliberately has no knowledge of
    nomic-embed-text's task-prefix convention ("search_document: "/"search_query: ")
    — that's specific to how each pipeline step uses the embedding, not to the
    client itself, so it's applied by the callers (step6_embedding.py,
    step3_embedding_question.py).
    """

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url or settings.embedding_base_url
        self._model_name = model_name or settings.embedding_model_name
        self._transport = transport

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches of settings.embedding_batch_size, preserving order.

        On CPU, Ollama's time per request grows with the number of inputs (~1.5s per
        200-word chunk measured locally), so sending a whole document in one request
        blows through the timeout for anything beyond ~20 chunks. Batching bounds the
        per-request time regardless of document size.
        """
        batch_size = max(1, settings.embedding_batch_size)
        timeout = httpx.Timeout(settings.embedding_request_timeout_seconds)
        embeddings: list[list[float]] = []
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as http_client:
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                embeddings.extend(await self._embed_batch(http_client, batch, start, len(texts)))
        return embeddings

    async def _embed_batch(
        self, http_client: httpx.AsyncClient, batch: list[str], start: int, total: int
    ) -> list[list[float]]:
        payload = {"model": self._model_name, "input": batch}
        try:
            response = await http_client.post(f"{self._base_url}/api/embed", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise EmbeddingModelError(
                f"Embedding request failed for texts {start + 1}-{start + len(batch)} "
                f"of {total}: {type(error).__name__} {error}".rstrip()
            ) from error
        embeddings: list[list[float]] = response.json()["embeddings"]
        return embeddings

    async def embed_text(self, text: str) -> list[float]:
        embeddings = await self.embed_texts([text])
        return embeddings[0]


embedding_client = EmbeddingClient()
