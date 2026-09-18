from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from rag_backend.llm_model.client import LlmClient, llm_client
from rag_backend.schemas.chat import ChatRequest, Citation
from rag_backend.storage import dummy_store

router = APIRouter(tags=["chat"])

# Separates the streamed answer text from the trailing citations payload.
# The real retrieval pipeline will replace this with proper SSE events.
_CITATIONS_MARKER = "\x00CITATIONS:"


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


def _build_system_prompt(citations: list[Citation]) -> str:
    if not citations:
        return (
            "You are a helpful assistant. No relevant documents were found for this "
            "question. Tell the user you don't know based on the available documents."
        )
    context = "\n".join(f"[{i + 1}] ({c.filename}) {c.excerpt}" for i, c in enumerate(citations))
    return (
        "You are a helpful assistant that answers questions using ONLY the context below. "
        "Keep answers brief. If the context doesn't contain the answer, say you don't know.\n\n"
        f"Context:\n{context}"
    )


async def _stream_answer(
    message: str, citations: list[Citation], client: LlmClient
) -> AsyncIterator[bytes]:
    messages = [
        {"role": "system", "content": _build_system_prompt(citations)},
        {"role": "user", "content": message},
    ]
    async for token in client.stream_chat(messages):
        yield token.encode("utf-8")

    citations_json = json.dumps([c.model_dump() for c in citations])
    yield f"{_CITATIONS_MARKER}{citations_json}".encode("utf-8")


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    citations = _pick_citations(request.message)
    return StreamingResponse(
        _stream_answer(request.message, citations, llm_client), media_type="text/plain"
    )
