"""Agents tab API: start a UI test-generation run and inspect every step's input/output.

Runs execute in the background (minutes on CPU); the UI polls GET /agents/runs/{id},
which returns the run record as it is being written. Records are only visible to their
creator and admins, like pipeline logs: they contain the full prompts and responses.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from rag_backend.agents import artifacts, handoff, pipeline, run_store
from rag_backend.agents.defaults import DEFAULT_REGISTER_REQUIREMENT
from rag_backend.agents.run_layout import run_dir
from rag_backend.auth.dependencies import CurrentUserDep
from rag_backend.config import settings
from rag_backend.exceptions import (
    AgentRunInProgressError,
    AgentRunNotFoundError,
    AgentTargetNotAllowedError,
)
from rag_backend.schemas.agents import (
    AgentDefaults,
    AgentModelInfo,
    AgentRunDetail,
    AgentRunRequest,
    AgentRunStarted,
    AgentRunSummary,
    AgentStepStatus,
)

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger(__name__)

# Run ids are uuid4s; the id is also a file-name component, so nothing else is accepted.
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_MEDIA_TYPES = {
    ".png": "image/png",
    ".ts": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}


def _summary(record: dict[str, Any]) -> AgentRunSummary:
    report = record.get("report") or {}
    steps = [
        AgentStepStatus(
            name=name,
            status=str(step.get("status", "unknown")),
            duration_ms=step.get("duration_ms"),
        )
        for name, step in (record.get("steps") or {}).items()
    ]
    return AgentRunSummary(
        run_id=record["run_id"],
        status=record["status"],
        created_at=record.get("created_at", ""),
        finished_at=record.get("finished_at"),
        username=record.get("created_by_username"),
        target_url=record.get("target_url", ""),
        current_step=record.get("current_step"),
        error=record.get("error"),
        passed=report.get("passed"),
        total=report.get("total"),
        steps=steps,
    )


def _load(run_id: str, user: CurrentUserDep) -> dict[str, Any]:
    if not _RUN_ID_PATTERN.match(run_id):
        raise HTTPException(status_code=404, detail="Agents run not found")
    try:
        return run_store.load_run(run_id, user)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Agents run not found") from error


@router.get("/defaults", response_model=AgentDefaults)
async def get_defaults(user: CurrentUserDep) -> AgentDefaults:
    return AgentDefaults(
        target_url=settings.agents_default_target_url,
        requirement=DEFAULT_REGISTER_REQUIREMENT,
        allowed_target_hosts=settings.agents_allowed_target_hosts,
        models={role: AgentModelInfo(**info) for role, info in pipeline.models_info().items()},
        max_design_rounds=settings.agents_max_design_rounds,
        active_run_id=pipeline.active_run_id(),
    )


@router.post("/runs", response_model=AgentRunStarted, status_code=202)
async def start_run(
    request: AgentRunRequest, user: CurrentUserDep, background_tasks: BackgroundTasks
) -> AgentRunStarted:
    try:
        record = pipeline.start_run(user, request.target_url, request.requirement)
    except AgentRunInProgressError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AgentTargetNotAllowedError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    background_tasks.add_task(pipeline.run_agents_pipeline, record)
    return AgentRunStarted(run_id=record["run_id"], status=record["status"])


@router.get("/runs", response_model=list[AgentRunSummary])
async def list_runs(user: CurrentUserDep) -> list[AgentRunSummary]:
    return [_summary(record) for record in run_store.list_runs(user)]


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
async def get_run(run_id: str, user: CurrentUserDep) -> AgentRunDetail:
    record = _load(run_id, user)
    return AgentRunDetail(run_id=run_id, status=record["status"], record=record)


@router.get("/runs/{run_id}/artifacts/{name:path}")
async def get_artifact(run_id: str, name: str, user: CurrentUserDep) -> FileResponse:
    """Any file of the run folder: evidence screenshots, test-case.md, README.md, the
    spec. `name` is the path relative to the run folder."""
    record = _load(run_id, user)  # ownership check
    root = run_dir(record)
    if not root.is_dir():
        root = artifacts.legacy_root(run_id)
    path = artifacts.resolve(root, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, media_type=_MEDIA_TYPES.get(path.suffix, "application/octet-stream"))


@router.get("/runs/{run_id}/handoff/{path:path}")
async def get_handoff_file(run_id: str, path: str, user: CurrentUserDep) -> FileResponse:
    """One of the run's per-agent input/output files (or a file copied next to one),
    `path` relative to agents_result_dir. Only paths this run recorded are served, so a
    user cannot read another run's files by guessing names."""
    record = _load(run_id, user)  # ownership check
    listed = handoff.listed_paths(record)
    allowed = path in listed or (
        Path(path).suffix in artifacts.SERVABLE_SUFFIXES
        and any(path.startswith(f"{folder}/") for folder in listed if folder.endswith("_files"))
    )
    resolved = handoff.resolve(path) if allowed else None
    if resolved is None:
        raise HTTPException(status_code=404, detail="Handoff file not found")
    return FileResponse(
        resolved, media_type=_MEDIA_TYPES.get(resolved.suffix, "application/octet-stream")
    )
