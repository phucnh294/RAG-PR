from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from rag_backend.agents.run_layout import RUN_FILE
from rag_backend.auth.dependencies import CurrentUserDep
from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.schemas.logs import LogDetail, LogSummary

router = APIRouter(prefix="/logs", tags=["logs"])
logger = logging.getLogger(__name__)

_PIPELINES = ("retrieval", "indexing", "agents")
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


def _owner_id(pipeline: str, record: dict[str, Any]) -> str | None:
    """Who a log belongs to: the asker (retrieval), the uploader (indexing) or whoever
    started the run (agents)."""
    owner = record.get("user_id") if pipeline == "retrieval" else record.get("created_by")
    return str(owner) if owner else None


def _can_view(user: CurrentUser, pipeline: str, record: dict[str, Any]) -> bool:
    """Admins see every log; everyone else only their own questions and uploads, since
    logs hold full messages, prompts and retrieved chunks."""
    return user.is_admin or _owner_id(pipeline, record) == user.id


def _summarize(pipeline: str, file_stem: str, record: dict[str, Any]) -> LogSummary:
    if pipeline == "retrieval":
        summary = str(record.get("user_message", ""))
        username = record.get("username")
    elif pipeline == "agents":
        report = record.get("report") or {}
        result = f" ({report['passed']}/{report['total']} passed)" if report else ""
        summary = f"{record.get('target_url', '?')} -> {record.get('status', '?')}{result}"
        username = record.get("created_by_username")
    else:
        summary = f"{record.get('filename', '?')} -> {record.get('status', '?')}"
        username = record.get("created_by_username")
    return LogSummary(
        id=file_stem,
        pipeline=pipeline,
        created_at=_parse_created_at(file_stem),
        summary=summary[:_SUMMARY_MAX_CHARS],
        username=str(username) if username else None,
    )


def _read_log_files(pipeline: str) -> list[tuple[str, Path]]:
    """(log id, file) pairs. An agents run is a folder whose record is {id}/run.json
    (see agents/run_layout.py); every other log, and agents runs from before that layout,
    is a flat {id}.json."""
    log_dir = settings.pipeline_log_dir / pipeline
    if not log_dir.exists():
        return []
    files = [(path.stem, path) for path in log_dir.glob("*.json")]
    if pipeline == "agents":
        files += [(path.parent.name, path) for path in log_dir.glob(f"*/{RUN_FILE}")]
    return files


def _log_path(pipeline: str, log_id: str) -> Path:
    log_dir = settings.pipeline_log_dir / pipeline
    folder_record = log_dir / log_id / RUN_FILE
    if pipeline == "agents" and folder_record.is_file():
        return folder_record
    return log_dir / f"{log_id}.json"


@router.get("", response_model=list[LogSummary])
async def list_logs(
    user: CurrentUserDep, pipeline: str | None = Query(default=None)
) -> list[LogSummary]:
    if pipeline is not None and pipeline not in _PIPELINES:
        raise HTTPException(status_code=400, detail=f"Unknown pipeline: {pipeline}")
    pipelines = (pipeline,) if pipeline is not None else _PIPELINES

    summaries: list[LogSummary] = []
    for name in pipelines:
        for log_id, path in _read_log_files(name):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("Skipping unreadable pipeline log file: %s", path)
                continue
            if _can_view(user, name, record):
                summaries.append(_summarize(name, log_id, record))

    summaries.sort(key=lambda item: item.id, reverse=True)
    return summaries[:_MAX_LOGS_RETURNED]


@router.get("/{pipeline}/{log_id}", response_model=LogDetail)
async def get_log(pipeline: str, log_id: str, user: CurrentUserDep) -> LogDetail:
    if pipeline not in _PIPELINES:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline: {pipeline}")
    if not _LOG_ID_PATTERN.match(log_id):
        raise HTTPException(status_code=404, detail="Log not found")

    path = _log_path(pipeline, log_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Log not found")

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Log file is unreadable") from error

    if not _can_view(user, pipeline, record):
        # 404, not 403: don't confirm another user's log exists.
        raise HTTPException(status_code=404, detail="Log not found")
    return LogDetail(id=log_id, pipeline=pipeline, record=record)
