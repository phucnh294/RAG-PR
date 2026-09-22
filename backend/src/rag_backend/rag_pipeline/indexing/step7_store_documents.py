from __future__ import annotations

from rag_backend.db import postgres_store
from rag_backend.exceptions import DocumentNotFoundError


async def store_document(document_id: str, excerpts: list[str]) -> None:
    """Mark the document ready and attach a few chunk excerpts used for chat citations."""
    updated = await postgres_store.update_document(document_id, status="ready", excerpts=excerpts)
    if updated is None:
        raise DocumentNotFoundError(f"Document {document_id} not found")
