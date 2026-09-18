from __future__ import annotations

from dataclasses import dataclass

from rag_backend.rag_pipeline.indexing.step2_document_parsing import ParsedDocument


@dataclass
class TextChunk:
    document_id: str
    chunk_index: int
    content: str
    char_offset_start: int
    char_offset_end: int


def chunk_text(
    parsed: ParsedDocument, chunk_size_words: int, overlap_words: int
) -> list[TextChunk]:
    """Split parsed text into fixed-size, overlapping chunks using a whitespace word split.

    Offsets are computed against the words rejoined with single spaces, so they are an
    approximation of the original text's exact whitespace/formatting, not exact byte offsets.
    """
    words = parsed.text.split()
    if not words:
        return []

    step = max(chunk_size_words - overlap_words, 1)
    chunks: list[TextChunk] = []
    position = 0
    chunk_index = 0

    while position < len(words):
        window = words[position : position + chunk_size_words]
        content = " ".join(window)
        prefix_length = len(" ".join(words[:position]))
        start_offset = prefix_length + 1 if position > 0 else 0
        end_offset = start_offset + len(content)

        chunks.append(
            TextChunk(
                document_id=parsed.document_id,
                chunk_index=chunk_index,
                content=content,
                char_offset_start=start_offset,
                char_offset_end=end_offset,
            )
        )
        chunk_index += 1
        position += step

    return chunks
