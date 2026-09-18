from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_hash: str
    mime_type: str
    size_bytes: int
    status: str
    created_at: datetime


class UploadResponse(BaseModel):
    document: DocumentOut
    already_exists: bool
