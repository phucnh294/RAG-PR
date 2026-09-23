from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from rag_backend.config import settings
from rag_backend.schemas.logs import LogDetail, LogSummary

router = APIRouter(prefix="/logs", tags=["logs"])
logger = logging.getLogger(__name__)

_PIPELINES = ("retrieval", "indexing")
_MAX_LOGS_RETURNED = 200
_SUMMARY_MAX_CHARS = 160
# Log filenames are always "{timestamp}_{uuid}" (see pipeline_logging.py) — enforcing
# this shape on the id path parameter blocks path traversal via "../" or "/".
_LOG_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _parse_created_at(file_stem: str) -> str:
    timestamp_part = file_stem.split("_", 1)[0]
    try:
        parsed = datetime.strptime(timestamp_part, "%Y%m%dT%H%M%S%f").replace(tzinfo=UTC)
        return parsed.isoformat()
    except ValueError:
        return timestamp_part


def _summarize(pipeline: str, file_stem: str, record: dict[str, Any]) -> LogSummary:
    if pipeline == "retrieval":
        summary = str(record.get("user_message", ""))
    else:
        summary = f"{record.get('filename', '?')} -> {record.get('status', '?')}"
    return LogSummary(
        id=file_stem,
        pipeline=pipeline,
        created_at=_parse_created_at(file_stem),
        summary=summary[:_SUMMARY_MAX_CHARS],
    )


def _read_log_files(pipeline: str) -> list[Path]:
    log_dir = settings.pipeline_log_dir / pipeline
    if not log_dir.exists():
        return []
    return list(log_dir.glob("*.json"))


@router.get("", response_model=list[LogSummary])
async def list_logs(pipeline: str | None = Query(default=None)) -> list[LogSummary]:
    if pipeline is not None and pipeline not in _PIPELINES:
        raise HTTPException(status_code=400, detail=f"Unknown pipeline: {pipeline}")
    pipelines = (pipeline,) if pipeline is not None else _PIPELINES

    summaries: list[LogSummary] = []
    for name in pipelines:
        for path in _read_log_files(name):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("Skipping unreadable pipeline log file: %s", path)
                continue
            summaries.append(_summarize(name, path.stem, record))

    summaries.sort(key=lambda item: item.id, reverse=True)
    return summaries[:_MAX_LOGS_RETURNED]


@router.get("/{pipeline}/{log_id}", response_model=LogDetail)
async def get_log(pipeline: str, log_id: str) -> LogDetail:
    if pipeline not in _PIPELINES:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline: {pipeline}")
    if not _LOG_ID_PATTERN.match(log_id):
        raise HTTPException(status_code=404, detail="Log not found")

    path = settings.pipeline_log_dir / pipeline / f"{log_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Log not found")

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Log file is unreadable") from error

    return LogDetail(id=log_id, pipeline=pipeline, record=record)
