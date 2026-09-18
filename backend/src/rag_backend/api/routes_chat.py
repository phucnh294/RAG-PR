from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from rag_backend.schemas.chat import ChatRequest, Citation
from rag_backend.storage import dummy_store

router = APIRouter(tags=["chat"])

# Separates the streamed answer text from the trailing citations payload.
# The real (non-dummy) retrieval pipeline will replace this with proper SSE events.
_CITATIONS_MARKER = "\x00CITATIONS:"

_WORD_DELAY_SECONDS = 0.04


def _pick_citations(message: str, limit: int = 2) -> list[Citation]:
    query_words = {word.lower() for word in message.split() if len(word) > 3}
    pairs = dummy_store.all_excerpts()

    def relevance(pair: tuple[dummy_store.DocumentRecord, str]) -> int:
        _, excerpt = pair
        excerpt_words = {word.lower().strip(".,") for word in excerpt.split()}
        return len(query_words & excerpt_words)

    ranked = sorted(pairs, key=relevance, reverse=True)[:limit]
    scores = [0.87, 0.73, 0.61, 0.55]
    return [
        Citation(
            document_id=doc.id,
            filename=doc.filename,
            excerpt=excerpt,
            similarity_score=scores[i] if i < len(scores) else 0.5,
        )
        for i, (doc, excerpt) in enumerate(ranked)
    ]


def _build_answer(citations: list[Citation]) -> str:
    if not citations:
        return "I don't know based on the available documents."
    excerpt_sentences = " ".join(c.excerpt for c in citations)
    return f"Based on the available documents: {excerpt_sentences}"


async def _stream_answer(answer: str, citations: list[Citation]) -> AsyncIterator[bytes]:
    for word in answer.split(" "):
        yield f"{word} ".encode("utf-8")
        await asyncio.sleep(_WORD_DELAY_SECONDS)
    citations_json = json.dumps([c.model_dump() for c in citations])
    yield f"{_CITATIONS_MARKER}{citations_json}".encode("utf-8")


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    citations = _pick_citations(request.message)
    answer = _build_answer(citations)
    return StreamingResponse(_stream_answer(answer, citations), media_type="text/plain")
