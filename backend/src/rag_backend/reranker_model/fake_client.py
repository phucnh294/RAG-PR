"""In-memory fake reranker client — deterministic, no network.

This is NOT used in production (see reranker_model/client.py for the real
text-embeddings-inference-backed cross-encoder client). The test suite's root
conftest.py monkeypatches rag_backend.reranker_model.client.reranker_client to an
instance of this class, so step 6 always calls "reranker_client.score(...)" while tests
exercise this stub instead of a real model.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")


class RerankerClient:
    """Scores a text by the fraction of the query's distinct words it contains.

    Crude, but it reacts to the question the way a relevance model should (more shared
    terms -> higher score), which is enough to test that step 6 reorders by score.
    """

    def __init__(self, model_name: str = "fake-cross-encoder") -> None:
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    async def score(self, query: str, texts: list[str]) -> list[float]:
        query_words = set(_WORD.findall(query.lower()))
        if not query_words:
            return [0.0 for _ in texts]
        return [
            len(query_words & set(_WORD.findall(text.lower()))) / len(query_words) for text in texts
        ]
