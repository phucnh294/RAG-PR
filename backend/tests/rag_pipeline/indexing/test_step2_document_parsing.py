from __future__ import annotations

import pytest

from rag_backend.exceptions import PdfParsingNotImplementedError
from rag_backend.rag_pipeline.indexing.step1_load_input import LoadedFile
from rag_backend.rag_pipeline.indexing.step2_document_parsing import parse_document


def test_parse_document_decodes_text_mime_types() -> None:
    loaded = LoadedFile(
        document_id="doc-1", filename="note.txt", mime_type="text/plain", raw_bytes=b"hello"
    )

    parsed = parse_document(loaded)

    assert parsed.text == "hello"


def test_parse_document_raises_for_pdf() -> None:
    loaded = LoadedFile(
        document_id="doc-1", filename="file.pdf", mime_type="application/pdf", raw_bytes=b"%PDF-1.4"
    )

    with pytest.raises(PdfParsingNotImplementedError):
        parse_document(loaded)
