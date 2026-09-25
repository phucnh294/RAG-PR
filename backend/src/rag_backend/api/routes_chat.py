from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from rag_backend.auth.dependencies import CurrentUserDep
from rag_backend.rag_pipeline.retrieval.pipeline import run_retrieval
from rag_backend.schemas.chat import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(request: ChatRequest, user: CurrentUserDep) -> StreamingResponse:
    return StreamingResponse(
        run_retrieval(request.message, user, rerank_enabled=request.rerank),
        media_type="text/plain",
    )
