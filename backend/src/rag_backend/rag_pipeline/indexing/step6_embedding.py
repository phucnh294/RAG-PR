from __future__ import annotations

import hashlib
from dataclasses import dataclass

from rag_backend.config import settings
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import ChunkWithMetadata


@dataclass
class EmbeddedChunk:
    chunk_with_metadata: ChunkWithMetadata
    embedding: list[float]


def _stub_embed(text: str) -> list[float]:
    """Deterministic placeholder embedding until a real embedding-model container exists.

    Hashes the text into a repeatable pseudo-random vector at settings.embedding_dimension
    (768, matching the dimension already fixed for nomic-embed-text in the architecture
    docs). Not semantically meaningful — replace with a real embedding-model client call.
    """
    dimension = settings.embedding_dimension
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    repeated = (digest * (dimension // len(digest) + 1))[:dimension]
    return [(byte / 255.0) * 2 - 1 for byte in repeated]


def embed_chunks(chunks: list[ChunkWithMetadata]) -> list[EmbeddedChunk]:
    return [
        EmbeddedChunk(chunk_with_metadata=chunk, embedding=_stub_embed(chunk.chunk.content))
        for chunk in chunks
    ]
