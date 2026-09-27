"""Folder layout of one agents run (the per-agent input/output files live separately,
in agents_result_dir — see handoff.py):

pipeline_log_dir/agents/{timestamp}_{run_id}/
    run.json                      full run record (what the Agents/Logs tabs read), incl.
                                  every LLM call's prompt and raw response
    README.md                     run summary with links to every agent file and test case
    capture/                      capture.png, capture_vision.png (page-capture agent)
    automation/                   the generated {suite}.spec.ts (test-automation agent)
    test-cases/
        TC-REG-001/
            test-case.md          the case: rules, data, steps, verdict, result, evidence
            result.json           raw execution result (per step status/observed/error)
            evidence/             step-01-goto.png ... one screenshot per executed step
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rag_backend.config import settings

RUN_FILE = "run.json"
CAPTURE_FOLDER = "capture"
AUTOMATION_FOLDER = "automation"
CASES_FOLDER = "test-cases"

# Path segments are built from LLM-chosen case ids, so they are sanitized on write and
# validated on read (blocks "../" traversal through the artifact route).
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$")
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def agents_root() -> Path:
    return settings.pipeline_log_dir / "agents"


def run_dir(record: dict[str, Any]) -> Path:
    return agents_root() / str(record["log_file_stem"])


def safe_segment(text: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", text).strip("._") or "item"
    return cleaned[:100]


def is_safe_relative(rel: str) -> bool:
    parts = rel.split("/")
    return bool(parts) and all(_SEGMENT.match(part) for part in parts)


def case_folder(case_id: str) -> str:
    return f"{CASES_FOLDER}/{safe_segment(case_id)}"


def write_text_atomic(path: Path, text: str) -> None:
    """Write-then-rename, so a reader polling a run in progress never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_json_atomic(path: Path, value: Any) -> None:
    write_text_atomic(path, json.dumps(value, indent=2, default=str, ensure_ascii=False))
