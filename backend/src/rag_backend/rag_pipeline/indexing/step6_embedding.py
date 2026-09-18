from __future__ import annotations

from dataclasses import dataclass

from rag_backend.embedding_model.client import EmbeddingClient, embedding_client
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import ChunkWithMetadata


@dataclass
class EmbeddedChunk:
    chunk_with_metadata: ChunkWithMetadata
    embedding: list[float]


def embed_chunks(
    chunks: list[ChunkWithMetadata], client: EmbeddingClient = embedding_client
) -> list[EmbeddedChunk]:
    texts = [chunk.chunk.content for chunk in chunks]
    embeddings = client.embed_texts(texts)
    return [
        EmbeddedChunk(chunk_with_metadata=chunk, embedding=embedding)
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
