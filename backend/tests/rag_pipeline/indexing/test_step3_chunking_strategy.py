from __future__ import annotations

from rag_backend.rag_pipeline.indexing.step2_document_parsing import ParsedDocument
from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import chunk_text


def _parsed(text: str) -> ParsedDocument:
    return ParsedDocument(document_id="doc-1", filename="f.txt", mime_type="text/plain", text=text)


def test_chunk_text_returns_empty_list_for_empty_text() -> None:
    assert chunk_text(_parsed(""), chunk_size_words=5, overlap_words=1) == []


def test_chunk_text_splits_into_expected_word_windows() -> None:
    text = "one two three four five six seven eight"
    chunks = chunk_text(_parsed(text), chunk_size_words=4, overlap_words=1)

    assert [c.content for c in chunks] == [
        "one two three four",
        "four five six seven",
        "seven eight",
    ]
    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_chunk_text_single_chunk_when_shorter_than_window() -> None:
    chunks = chunk_text(_parsed("one two"), chunk_size_words=10, overlap_words=2)

    assert len(chunks) == 1
    assert chunks[0].content == "one two"
