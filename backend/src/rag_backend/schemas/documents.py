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
    classification: str
    tags: list[str]
    created_by: str | None
    created_by_username: str | None
    # Whether the CALLER may delete it (creator or admin) — lets the UI hide the button.
    can_delete: bool


class UploadResponse(BaseModel):
    document: DocumentOut
    already_exists: bool
