"""One agents run = one folder (see run_layout.py) holding run.json, rewritten after every
step and every LLM call so the Agents tab can poll progress, plus per-agent and per-test-case
files. The Logs tab lists run.json too (routes_logs, pipeline "agents").

Runs from before the folder layout (a flat pipeline_log_dir/agents/{stem}.json) are still
listed and readable."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rag_backend.agents import handoff
from rag_backend.agents.run_files import write_run_files
from rag_backend.agents.run_layout import RUN_FILE, agents_root, run_dir, write_json_atomic
from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.exceptions import AgentRunNotFoundError
from rag_backend.pipeline_logging import StepRecorder, new_log_file_stem

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = frozenset({"queued", "running"})

# The run this backend process is executing (one at a time, see pipeline.start_run). Kept
# here, not in pipeline.py, so effective_status can tell a live run from one that was
# interrupted by a restart without importing the pipeline.
_active_run_id: str | None = None


def active_run_id() -> str | None:
    return _active_run_id


def set_active_run(run_id: str | None) -> None:
    global _active_run_id
    _active_run_id = run_id


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class AgentContext:
    """Everything a step needs to log itself: the run record and its StepRecorder."""

    run_id: str
    record: dict[str, Any]
    recorder: StepRecorder

    @property
    def root(self) -> Path:
        """The run folder every file of this run goes into."""
        return run_dir(self.record)

    def persist(self) -> None:
        persist(self.record)

    def begin(self, step: str, input_data: Any) -> None:
        """Log the step's input and write its input handoff file (handoff.py)."""
        self.record["current_step"] = step
        self.recorder.log_input(step, input_data)
        handoff.write_input(self.record, step, input_data)
        self.persist()

    def finish(self, step: str, output: Any, checks: list[Any]) -> None:
        """Log the step's output and write its output handoff file: the file the next
        agent's input is parsed from."""
        self.recorder.log_extra(step, "checks", checks)
        self.recorder.log_output(step, output)
        handoff.write_output(self.record, step)
        self.persist()

    def fail(self, step: str, error: str) -> None:
        """Mark the step failed; its output file is (re)written with the error, so the
        chain on disk shows where it stopped and why."""
        self.recorder.mark_failed(step, error)
        try:
            handoff.write_output(self.record, step)
        except OSError:
            logger.exception("Could not write the failed output file of %s", step)
        self.persist()


def new_run_record(
    run_id: str,
    user: CurrentUser,
    target_url: str,
    requirement: str,
    models: dict[str, dict[str, str]],
) -> dict[str, Any]:
    now = now_iso()
    return {
        "run_id": run_id,
        "log_file_stem": new_log_file_stem(run_id),
        "pipeline": "agents",
        "status": "queued",
        "created_by": user.id,
        "created_by_username": user.username,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "updated_at": now,
        "target_url": target_url,
        "requirement": requirement,
        "models": models,
        "current_step": None,
        "error": None,
        "steps": {},
        "report": None,
    }


def persist(record: dict[str, Any]) -> None:
    record["updated_at"] = now_iso()
    write_json_atomic(run_dir(record) / RUN_FILE, record)
    write_run_files(record)


def run_record_paths() -> list[Path]:
    """Every run's record file, newest first: {stem}/run.json, plus legacy {stem}.json."""
    root = agents_root()
    if not root.exists():
        return []
    paths = [*root.glob(f"*/{RUN_FILE}"), *root.glob("*.json")]
    return sorted(paths, key=_stem_of, reverse=True)


def _stem_of(path: Path) -> str:
    return path.parent.name if path.name == RUN_FILE else path.stem


def _read(path: Path) -> dict[str, Any] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Skipping unreadable agents run log: %s", path)
        return None
    return record if isinstance(record, dict) else None


def effective_status(record: dict[str, Any]) -> str:
    """The stored status, except a queued/running run is "stale" when this process is not
    executing it (the backend restarted mid-run) or it stopped updating (a call hung past
    its timeout). Without this, an interrupted run would look alive and block new runs in
    the UI."""
    status = str(record.get("status", "unknown"))
    if status not in _ACTIVE_STATUSES:
        return status
    if record.get("run_id") != _active_run_id:
        return "stale"
    try:
        updated = datetime.fromisoformat(str(record.get("updated_at")))
    except ValueError:
        return "stale"
    age = (datetime.now(UTC) - updated).total_seconds()
    return "stale" if age > settings.agents_run_timeout_seconds else status


def can_view(user: CurrentUser, record: dict[str, Any]) -> bool:
    return user.is_admin or record.get("created_by") == user.id


def load_run(run_id: str, user: CurrentUser) -> dict[str, Any]:
    """The run's record; AgentRunNotFoundError when missing OR owned by someone else."""
    matches = [path for path in run_record_paths() if _stem_of(path).endswith(f"_{run_id}")]
    record = _read(matches[0]) if matches else None
    if record is None or not can_view(user, record):
        raise AgentRunNotFoundError(f"Agents run {run_id} not found")
    record["status"] = effective_status(record)
    return record


def list_runs(user: CurrentUser, limit: int = 50) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in run_record_paths():
        record = _read(path)
        if record is None or not can_view(user, record):
            continue
        record["status"] = effective_status(record)
        records.append(record)
        if len(records) >= limit:
            break
    return records
