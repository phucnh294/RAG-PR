from __future__ import annotations

from rag_backend.exceptions import DocumentNotFoundError
from rag_backend.storage import dummy_store


def store_document(document_id: str, excerpts: list[str]) -> None:
    """Mark the document ready and attach a few chunk excerpts used for dummy chat citations."""
    updated = dummy_store.update_document(document_id, status="ready", excerpts=excerpts)
    if updated is None:
        raise DocumentNotFoundError(f"Document {document_id} not found")
