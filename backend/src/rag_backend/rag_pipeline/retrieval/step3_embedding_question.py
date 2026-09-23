from __future__ import annotations

from dataclasses import dataclass

from rag_backend.embedding_model import client as embedding_model_client
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import NormalizedQuery

# nomic-embed-text expects queries to be prefixed this way for best retrieval
# quality (paired with "search_document: " on the indexed-passage side, see
# indexing/step6_embedding.py). Only the text sent to the embedding call is
# prefixed — EmbeddedQuery.text stays the original, unprefixed question.
_QUERY_PREFIX = "search_query: "


@dataclass
class EmbeddedQuery:
    text: str
    embedding: list[float]
    document_ids: list[str] | None = None


async def embed_question(query: NormalizedQuery) -> EmbeddedQuery:
    """Embed the normalized question via the embedding-model container.

    Looks up embedding_model_client.embedding_client on every call (rather than
    binding it as a default argument) so tests can monkeypatch the module-level
    singleton.
    """
    embedding = await embedding_model_client.embedding_client.embed_text(_QUERY_PREFIX + query.text)
    return EmbeddedQuery(text=query.text, embedding=embedding, document_ids=query.document_ids)
