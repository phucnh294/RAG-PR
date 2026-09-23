from __future__ import annotations

import json
import logging
import re
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


async def test_run_indexing_writes_a_json_log_file_for_success_and_failure() -> None:
    ready_record = await dummy_store.add_document(
        filename="note.txt", content_hash="h3", mime_type="text/plain", size_bytes=11
    )
    doc_dir = settings.input_dir / ready_record.id
    doc_dir.mkdir(parents=True)
    (doc_dir / ready_record.filename).write_text("hello world, this is a test", encoding="utf-8")
    await run_indexing(ready_record.id, ready_record.filename, ready_record.mime_type)

    failed_record = await dummy_store.add_document(
        filename="file.pdf", content_hash="h4", mime_type="application/pdf", size_bytes=8
    )
    doc_dir = settings.input_dir / failed_record.id
    doc_dir.mkdir(parents=True)
    (doc_dir / failed_record.filename).write_bytes(b"%PDF-1.4")
    await run_indexing(failed_record.id, failed_record.filename, failed_record.mime_type)

    log_files = {
        path.stem.split("_", 1)[1]: path
        for path in (settings.pipeline_log_dir / "indexing").glob("*.json")
    }

    ready_log = json.loads(log_files[ready_record.id].read_text(encoding="utf-8"))
    assert ready_log["status"] == "ready"
    assert ready_log["chunk_count"] > 0
    assert ready_log["steps"]["6_embedding"]["duration_ms"] >= 0
    assert ready_log["steps"]["6_embedding"]["output"]["chunk_count"] == ready_log["chunk_count"]
    assert ready_log["steps"]["3_chunking_strategy"]["output"]["chunk_count"] > 0

    failed_log = json.loads(log_files[failed_record.id].read_text(encoding="utf-8"))
    assert failed_log["status"] == "failed"
    assert failed_log["error"] is not None
    assert "1_load_input" in failed_log["steps"]
    assert "3_chunking_strategy" not in failed_log["steps"]
    # step2 raised before store_document ran, so it logged its input but never got
    # to log an output — that gap is exactly what marks it as the failure point.
    assert "input" in failed_log["steps"]["2_document_parsing"]
    assert "output" not in failed_log["steps"]["2_document_parsing"]


async def test_run_indexing_logs_every_step_input_and_output_to_console(
    caplog: pytest.LogCaptureFixture,
) -> None:
    record = await dummy_store.add_document(
        filename="note.txt", content_hash="h5", mime_type="text/plain", size_bytes=11
    )
    doc_dir = settings.input_dir / record.id
    doc_dir.mkdir(parents=True)
    (doc_dir / record.filename).write_text("hello world, this is a test", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="rag_backend.rag_pipeline.indexing.pipeline"):
        await run_indexing(record.id, record.filename, record.mime_type)

    messages = [log_record.message for log_record in caplog.records]
    template = re.compile(r"^Indexing - \S+ \S+T\S+ - (input|output): ")
    assert any(template.match(m) for m in messages), messages

    def _has(step: str, direction: str) -> bool:
        return any(
            m.startswith(f"Indexing - {step} ") and f"- {direction}: " in m for m in messages
        )

    assert _has("1_load_input", "input")
    assert _has("1_load_input", "output")
    assert _has("8_store_chunks", "input")
    assert _has("8_store_chunks", "output")
