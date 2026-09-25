from __future__ import annotations

from rag_backend.rag_pipeline.indexing.frontmatter import parse_frontmatter
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


_QANDA_DOC = """---
title: Replay Trap
date: 2026-07-04
type: qanda
area: agentic-crawler
tags: [crawler, replay]
classification: internal
---

# Replay Trap

## TL;DR
- **What:** the crawler replays stale steps.

## Q1: Why does the crawler loop?
Because the replay cache is keyed by URL only.

### Detail
The key ignores form state.

## Q2: How was it fixed?
The key now includes the DOM hash.
"""


def _markdown(text: str) -> ParsedDocument:
    parsed = ParsedDocument(
        document_id="doc-1", filename="f.md", mime_type="text/markdown", text=text
    )
    parsed.frontmatter = parse_frontmatter(text)
    return parsed


def test_qanda_doc_gets_one_chunk_per_question_plus_tldr() -> None:
    chunks = chunk_text(_markdown(_QANDA_DOC), chunk_size_words=200, overlap_words=20)

    assert [chunk.section_heading for chunk in chunks] == [
        "TL;DR",
        "Q1: Why does the crawler loop?",
        "Q2: How was it fixed?",
    ]
    assert {chunk.strategy for chunk in chunks} == {"qanda"}
    assert [chunk.question_id for chunk in chunks] == [None, "Q1", "Q2"]
    # A ### sub-heading stays inside its question's chunk.
    assert "form state" in chunks[1].content
    assert chunks[1].content.startswith(
        "Title: Replay Trap | Section: Q1: Why does the crawler loop?"
    )


def test_q_headings_mean_qanda_even_without_frontmatter() -> None:
    text = "## Q1: One?\nYes.\n\n## Q2: Two?\nNo.\n"

    chunks = chunk_text(_markdown(text), chunk_size_words=200, overlap_words=20)

    assert [chunk.question_id for chunk in chunks] == ["Q1", "Q2"]
    assert chunks[0].content.startswith("Title: f.md | Section: Q1: One?")


def test_markdown_with_plain_sections_uses_section_strategy_and_keeps_preamble() -> None:
    text = "# Guide\nIntro words here.\n\n## Setup\nInstall it.\n\n## Usage\nRun it.\n"

    chunks = chunk_text(_markdown(text), chunk_size_words=200, overlap_words=20)

    assert [chunk.section_heading for chunk in chunks] == ["Introduction", "Setup", "Usage"]
    assert {chunk.strategy for chunk in chunks} == {"section"}
    assert "# Guide" not in chunks[0].content


def test_oversized_section_is_sub_split_and_every_piece_keeps_the_prefix() -> None:
    text = "## Q1: Long?\n" + " ".join(f"w{i}" for i in range(10)) + "\n"

    chunks = chunk_text(_markdown(text), chunk_size_words=4, overlap_words=1)

    assert len(chunks) == 3
    assert all(chunk.content.startswith("Title: f.md | Section: Q1: Long?") for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]


def test_markdown_without_headings_and_plain_text_fall_back_to_windows() -> None:
    markdown = chunk_text(_markdown("just some words"), chunk_size_words=10, overlap_words=2)
    plain = chunk_text(_parsed("## Q1: not markdown"), chunk_size_words=10, overlap_words=2)

    assert [chunk.strategy for chunk in markdown] == ["window"]
    assert [chunk.strategy for chunk in plain] == ["window"]


def test_parse_frontmatter_reads_schema_fields_and_tldr() -> None:
    parsed = parse_frontmatter(_QANDA_DOC)

    assert parsed is not None
    assert parsed.title == "Replay Trap"
    assert parsed.doc_type == "qanda"
    assert str(parsed.doc_date) == "2026-07-04"
    assert parsed.area == "agentic-crawler"
    assert parsed.tags == ["crawler", "replay"]
    assert parsed.classification == "internal"
    assert parsed.tldr == "- **What:** the crawler replays stale steps."


def test_parse_frontmatter_ignores_missing_or_malformed_blocks() -> None:
    assert parse_frontmatter("# Heading\n---\ntitle: x\n---\n") is None
    assert parse_frontmatter("---\ntitle: [unclosed\n---\nbody") is None
