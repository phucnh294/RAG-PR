from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LogSummary(BaseModel):
    id: str
    pipeline: str
    created_at: str
    summary: str
    username: str | None = None


class LogDetail(BaseModel):
    id: str
    pipeline: str
    record: dict[str, Any]
