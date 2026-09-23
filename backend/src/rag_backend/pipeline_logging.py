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
import uuid
from datetime import UTC, datetime
from typing import Any

from rag_backend.config import settings

logger = logging.getLogger(__name__)


def new_request_id() -> str:
    return str(uuid.uuid4())


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
