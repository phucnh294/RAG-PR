from __future__ import annotations

from dataclasses import dataclass

from rag_backend.embedding_model import client as embedding_model_client
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import ChunkWithMetadata

# nomic-embed-text expects indexed passages to be prefixed this way for best
# retrieval quality (paired with "search_query: " on the question side, see
# retrieval/step3_embedding_question.py).
_DOCUMENT_PREFIX = "search_document: "


@dataclass
class EmbeddedChunk:
    chunk_with_metadata: ChunkWithMetadata
    embedding: list[float]


async def embed_chunks(chunks: list[ChunkWithMetadata]) -> list[EmbeddedChunk]:
    """Embed every chunk's content via the embedding-model container.

    Looks up embedding_model_client.embedding_client on every call (rather than
    binding it as a default argument) so tests can monkeypatch the module-level
    singleton.
    """
    texts = [_DOCUMENT_PREFIX + chunk.chunk.content for chunk in chunks]
    embeddings = await embedding_model_client.embedding_client.embed_texts(texts)
    return [
        EmbeddedChunk(chunk_with_metadata=chunk, embedding=embedding)
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
