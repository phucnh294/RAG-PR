from __future__ import annotations

from dataclasses import dataclass

from rag_backend.embedding_model.client import EmbeddingClient, embedding_client
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import NormalizedQuery


@dataclass
class EmbeddedQuery:
    text: str
    embedding: list[float]
    document_ids: list[str] | None = None


def embed_question(
    query: NormalizedQuery, client: EmbeddingClient = embedding_client
) -> EmbeddedQuery:
    """Embed the normalized question using the same embedding client/dimension as indexing."""
    embedding = client.embed_text(query.text)
    return EmbeddedQuery(text=query.text, embedding=embedding, document_ids=query.document_ids)
