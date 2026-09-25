from __future__ import annotations

import re
from dataclasses import dataclass

from rag_backend.rag_pipeline.indexing.step2_document_parsing import ParsedDocument

STRATEGY_WINDOW = "window"
STRATEGY_SECTION = "section"
STRATEGY_QANDA = "qanda"

_H2_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_H1_LINE_RE = re.compile(r"^#[ \t]+.*$", re.MULTILINE)
_QUESTION_RE = re.compile(r"^Q(\d+)\b", re.IGNORECASE)
_PREAMBLE_HEADING = "Introduction"


@dataclass
class TextChunk:
    document_id: str
    chunk_index: int
    content: str
    char_offset_start: int
    char_offset_end: int
    strategy: str = STRATEGY_WINDOW
    section_heading: str | None = None
    question_id: str | None = None


@dataclass
class _Section:
    heading: str | None
    text: str
    start: int
    end: int


def chunk_text(
    parsed: ParsedDocument, chunk_size_words: int, overlap_words: int
) -> list[TextChunk]:
    """Split a document into chunks, choosing the strategy from its structure.

    - qanda:   markdown whose frontmatter says `type: qanda`, or that has `## Q<n>`
               headings — one chunk per question, so a retrieved chunk carries exactly
               one question and its whole answer.
    - section: other markdown with `##` headings — one chunk per section.
    - window:  everything else — fixed-size overlapping word windows.

    Every section chunk is prefixed with "Title: ... | Section: ..." so it stays
    self-contained when retrieved alone. A section longer than chunk_size_words is
    sub-split into word windows that each keep that prefix.
    """
    if parsed.is_markdown:
        sections = _split_sections(parsed)
        if any(section.heading for section in sections):
            return _section_chunks(parsed, sections, chunk_size_words, overlap_words)
    return _window_chunks(parsed, chunk_size_words, overlap_words)


def _word_windows(words: list[str], size: int, overlap: int) -> list[tuple[int, list[str]]]:
    """(start word index, window) pairs covering `words` with the given overlap.

    Stops at the first window that reaches the end, so no trailing window is ever just
    a tail already contained in the previous one.
    """
    step = max(size - overlap, 1)
    windows: list[tuple[int, list[str]]] = []
    for position in range(0, len(words), step):
        windows.append((position, words[position : position + size]))
        if position + size >= len(words):
            break
    return windows


def _window_chunks(
    parsed: ParsedDocument, chunk_size_words: int, overlap_words: int
) -> list[TextChunk]:
    """Offsets are computed against the words rejoined with single spaces, so they are an
    approximation of the original text's exact whitespace/formatting, not byte offsets.
    """
    words = parsed.text.split()
    chunks: list[TextChunk] = []
    for chunk_index, (position, window) in enumerate(
        _word_windows(words, chunk_size_words, overlap_words)
    ):
        content = " ".join(window)
        prefix_length = len(" ".join(words[:position]))
        start_offset = prefix_length + 1 if position > 0 else 0
        chunks.append(
            TextChunk(
                document_id=parsed.document_id,
                chunk_index=chunk_index,
                content=content,
                char_offset_start=start_offset,
                char_offset_end=start_offset + len(content),
            )
        )
    return chunks


def _split_sections(parsed: ParsedDocument) -> list[_Section]:
    """Cut the body (text after any frontmatter) at every `##` heading. Offsets point
    into the original text. The preamble before the first heading loses its `#` title
    line, which the chunk prefix already carries."""
    frontmatter = parsed.frontmatter
    body = frontmatter.body if frontmatter is not None else parsed.text
    base = frontmatter.body_offset if frontmatter is not None else 0

    headings = list(_H2_RE.finditer(body))
    sections: list[_Section] = []
    preamble_end = headings[0].start() if headings else len(body)
    preamble = _H1_LINE_RE.sub("", body[:preamble_end])
    sections.append(_Section(None, preamble, base, base + preamble_end))

    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        sections.append(
            _Section(
                heading.group(1).strip(),
                body[heading.end() : end],
                base + heading.start(),
                base + end,
            )
        )
    return sections


def _section_chunks(
    parsed: ParsedDocument, sections: list[_Section], chunk_size_words: int, overlap_words: int
) -> list[TextChunk]:
    frontmatter = parsed.frontmatter
    is_qanda = (frontmatter is not None and frontmatter.doc_type == STRATEGY_QANDA) or any(
        section.heading and _QUESTION_RE.match(section.heading) for section in sections
    )
    strategy = STRATEGY_QANDA if is_qanda else STRATEGY_SECTION
    title = (frontmatter.title if frontmatter is not None else None) or parsed.filename

    chunks: list[TextChunk] = []
    for section in sections:
        words = section.text.split()
        if not words:
            continue
        heading = section.heading or _PREAMBLE_HEADING
        question = _QUESTION_RE.match(heading)
        windows = (
            [window for _, window in _word_windows(words, chunk_size_words, overlap_words)]
            if len(words) > chunk_size_words
            else [words]
        )
        for window in windows:
            chunks.append(
                TextChunk(
                    document_id=parsed.document_id,
                    chunk_index=len(chunks),
                    content=f"Title: {title} | Section: {heading}\n" + " ".join(window),
                    char_offset_start=section.start,
                    char_offset_end=section.end,
                    strategy=strategy,
                    section_heading=heading,
                    question_id=f"Q{question.group(1)}" if question else None,
                )
            )
    return chunks
