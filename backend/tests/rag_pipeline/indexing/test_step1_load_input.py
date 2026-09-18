from __future__ import annotations

from pathlib import Path

import pytest

from rag_backend.config import settings
from rag_backend.rag_pipeline.indexing.step1_load_input import load_input


def test_load_input_reads_raw_bytes_from_input_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "input_dir", tmp_path)
    doc_dir = tmp_path / "doc-1"
    doc_dir.mkdir()
    (doc_dir / "note.txt").write_bytes(b"hello world")

    loaded = load_input(document_id="doc-1", filename="note.txt", mime_type="text/plain")

    assert loaded.raw_bytes == b"hello world"
    assert loaded.document_id == "doc-1"
    assert loaded.mime_type == "text/plain"
