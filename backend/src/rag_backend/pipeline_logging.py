"""Writes one JSON file per indexing/retrieval run under pipeline_log_dir.

This is separate from the console logging configured in logging_config.py: the
console gets a line-by-line trace of step start/end timings, while this module
captures the full record of a single run (user message, system prompt, retrieved
chunks, final answer, or the failure) as one self-contained file, so a single
exchange can be inspected without grepping through interleaved request logs.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from rag_backend.config import settings

logger = logging.getLogger(__name__)


def new_request_id() -> str:
    return str(uuid.uuid4())


class StepRecorder:
    """Logs and records both the input and output of every pipeline step.

    Each call to log_input/log_output emits one console line following the
    template "{process_name} - {step_name} {timestamp} - input|output: {data}",
    so an entire run can be read start-to-end straight from the console. The same
    data is written into record["steps"][step_name] for the per-run JSON file
    (see write_retrieval_log/write_indexing_log), so both views stay in sync.
    """

    def __init__(self, logger_: logging.Logger, process_name: str, record: dict[str, Any]) -> None:
        self._logger = logger_
        self._process_name = process_name
        self._record = record
        self._started_at: dict[str, float] = {}

    def log_input(self, step_name: str, data: Any) -> None:
        timestamp = datetime.now(UTC).isoformat()
        self._logger.info("%s - %s %s - input: %s", self._process_name, step_name, timestamp, data)
        self._record["steps"][step_name] = {"input": data, "input_at": timestamp}
        self._started_at[step_name] = time.monotonic()

    def log_output(self, step_name: str, data: Any) -> None:
        timestamp = datetime.now(UTC).isoformat()
        self._logger.info("%s - %s %s - output: %s", self._process_name, step_name, timestamp, data)
        started_at = self._started_at.pop(step_name, None)
        duration_ms = round((time.monotonic() - started_at) * 1000, 1) if started_at else 0.0
        self._record["steps"].setdefault(step_name, {})
        self._record["steps"][step_name].update(
            {"output": data, "output_at": timestamp, "duration_ms": duration_ms}
        )


def _write_json(subdir: str, file_stem: str, record: dict[str, Any]) -> None:
    log_dir = settings.pipeline_log_dir / subdir
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{file_stem}.json"
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote pipeline log: %s", path)


def write_retrieval_log(record: dict[str, Any]) -> None:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    _write_json("retrieval", f"{timestamp}_{record['request_id']}", record)


def write_indexing_log(record: dict[str, Any]) -> None:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    _write_json("indexing", f"{timestamp}_{record['document_id']}", record)
