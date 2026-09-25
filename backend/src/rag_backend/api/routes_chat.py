from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from rag_backend.auth.dependencies import CurrentUserDep
from rag_backend.conversations import service as conversation_service
from rag_backend.rag_pipeline.retrieval.pipeline import run_retrieval
from rag_backend.schemas.chat import ChatRequest

router = APIRouter(tags=["chat"])

CONVERSATION_ID_HEADER = "X-Conversation-Id"


@router.post("/chat")
async def chat(request: ChatRequest, user: CurrentUserDep) -> StreamingResponse:
    """Answer one message of a conversation (a new one when conversation_id is omitted).

    The conversation is resolved and the question saved BEFORE streaming starts, so an
    unknown or foreign conversation_id is a real 404 rather than a broken 200 stream.
    """
    conversation = await conversation_service.resolve_conversation(
        user, request.conversation_id, request.message
    )
    await conversation_service.record_question(conversation.id, request.message)
    return StreamingResponse(
        run_retrieval(
            request.message,
            user,
            rerank_enabled=request.rerank,
            conversation_id=conversation.id,
            memory_enabled=request.memory_enabled,
            memory_turns=request.memory_turns,
        ),
        media_type="text/plain",
        headers={CONVERSATION_ID_HEADER: conversation.id},
    )
