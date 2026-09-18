from __future__ import annotations

import re
from dataclasses import replace

from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import TextChunk

_WHITESPACE_RE = re.compile(r"\s+")


def preprocess_chunks(chunks: list[TextChunk]) -> list[TextChunk]:
    """Normalize each chunk's text: collapse repeated whitespace and strip leading/trailing space.

    Char offsets on the returned chunks still refer to the pre-cleaning text from
    step3, since cleaning can shorten content in ways that don't map 1:1 to offsets.
    """
    return [
        replace(chunk, content=_WHITESPACE_RE.sub(" ", chunk.content).strip()) for chunk in chunks
    ]
