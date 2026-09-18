from __future__ import annotations

import hashlib
import math

from rag_backend.config import settings


class EmbeddingClient:
    """Placeholder embedding client used by both indexing and retrieval.

    Produces a deterministic bag-of-words "hashing trick" embedding: each word is
    hashed into a dimension and sign, then the vector is L2-normalized. This gives
    meaningfully higher cosine similarity to texts that share vocabulary (unlike
    hashing the whole string, which would produce uncorrelated random vectors), so
    similarity search behaves sensibly for demos — but it is not a real semantic
    embedding. Replace with a call to a dedicated embedding-model container
    (e.g. nomic-embed-text via Ollama) once one exists; keep the same output
    dimension (settings.embedding_dimension) so stored vectors stay comparable.
    """

    def __init__(self, dimension: int | None = None) -> None:
        self._dimension = dimension or settings.embedding_dimension

    def embed_text(self, text: str) -> list[float]:
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

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


embedding_client = EmbeddingClient()
