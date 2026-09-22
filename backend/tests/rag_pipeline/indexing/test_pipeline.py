from __future__ import annotations

from pathlib import Path

import pytest

from rag_backend.config import settings
from rag_backend.rag_pipeline.indexing.pipeline import run_indexing
from rag_backend.storage import dummy_store


@pytest.fixture(autouse=True)
def _isolated_input_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "input_dir", tmp_path)


async def test_run_indexing_marks_document_ready_and_stores_chunks() -> None:
    record = await dummy_store.add_document(
        filename="note.txt", content_hash="h1", mime_type="text/plain", size_bytes=11
    )
    doc_dir = settings.input_dir / record.id
    doc_dir.mkdir(parents=True)
    (doc_dir / record.filename).write_text("hello world, this is a test document", encoding="utf-8")

    await run_indexing(record.id, record.filename, record.mime_type)

    updated = await dummy_store.get_document(record.id)
    assert updated is not None
    assert updated.status == "ready"
    assert len(updated.excerpts) > 0

    chunks = await dummy_store.get_chunks(record.id)
    assert len(chunks) > 0
    assert all(len(chunk.embedding) == settings.embedding_dimension for chunk in chunks)


async def test_run_indexing_marks_document_failed_for_unsupported_pdf() -> None:
    record = await dummy_store.add_document(
        filename="file.pdf", content_hash="h2", mime_type="application/pdf", size_bytes=8
    )
    doc_dir = settings.input_dir / record.id
    doc_dir.mkdir(parents=True)
    (doc_dir / record.filename).write_bytes(b"%PDF-1.4")

    await run_indexing(record.id, record.filename, record.mime_type)

    updated = await dummy_store.get_document(record.id)
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error_message is not None
    assert await dummy_store.get_chunks(record.id) == []
