from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from rag_backend.rag_pipeline.retrieval.pipeline import run_retrieval
from rag_backend.schemas.chat import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(run_retrieval(request.message), media_type="text/plain")
