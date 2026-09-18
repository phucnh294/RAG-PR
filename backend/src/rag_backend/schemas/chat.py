from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class Citation(BaseModel):
    document_id: str
    filename: str
    excerpt: str
    similarity_score: float
