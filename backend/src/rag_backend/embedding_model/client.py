from __future__ import annotations

import httpx

from rag_backend.config import settings


class EmbeddingClient:
    """Thin client for the dedicated embedding-model container's /api/embed endpoint.

    Mirrors llm_model/client.py's shape. Deliberately has no knowledge of
    nomic-embed-text's task-prefix convention ("search_document: "/"search_query: ")
    — that's specific to how each pipeline step uses the embedding, not to the
    client itself, so it's applied by the callers (step6_embedding.py,
    step3_embedding_question.py).
    """

    def __init__(self, base_url: str | None = None, model_name: str | None = None) -> None:
        self._base_url = base_url or settings.embedding_base_url
        self._model_name = model_name or settings.embedding_model_name

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self._model_name, "input": texts}
        timeout = httpx.Timeout(settings.embedding_request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            response = await http_client.post(f"{self._base_url}/api/embed", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["embeddings"]

    async def embed_text(self, text: str) -> list[float]:
        embeddings = await self.embed_texts([text])
        return embeddings[0]


embedding_client = EmbeddingClient()
