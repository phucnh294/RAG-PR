from __future__ import annotations

import pytest

from rag_backend.exceptions import DocumentNotFoundError
from rag_backend.rag_pipeline.indexing.step7_store_documents import store_document
from rag_backend.storage import dummy_store


async def test_store_document_marks_ready_with_excerpts() -> None:
    record = await dummy_store.add_document(
        filename="f.txt", content_hash="h1", mime_type="text/plain", size_bytes=10
    )

    await store_document(record.id, excerpts=["hello world"])

    updated = await dummy_store.get_document(record.id)
    assert updated is not None
    assert updated.status == "ready"
    assert updated.excerpts == ["hello world"]


async def test_store_document_raises_for_unknown_document() -> None:
    with pytest.raises(DocumentNotFoundError):
        await store_document("does-not-exist", excerpts=[])
