"""In-memory fake embedding client — deterministic, no network.

This is NOT used in production (see embedding_model/client.py for the real
Ollama/nomic-embed-text-backed client) — it exists purely as a fast,
dependency-free test double. The test suite's root conftest.py monkeypatches
rag_backend.embedding_model.client.embedding_client to an instance of this class,
so pipeline code always calls "embedding_client.embed_text(...)" while tests
transparently exercise this hash-based stub instead of a real model.
"""

from __future__ import annotations

import hashlib
import math

from rag_backend.config import settings


class EmbeddingClient:
    """Produces a deterministic bag-of-words "hashing trick" embedding: each word is
    hashed into a dimension and sign, then the vector is L2-normalized. This gives
    meaningfully higher cosine similarity to texts that share vocabulary (unlike
    hashing the whole string, which would produce uncorrelated random vectors), so
    similarity search behaves sensibly in tests — but it is not a real semantic
    embedding.
    """

    def __init__(self, dimension: int | None = None) -> None:
        self._dimension = dimension or settings.embedding_dimension

    async def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        words = text.lower().split()
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]
