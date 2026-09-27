"""Per-agent handoff files: each agent's output file is the next agent's input.

agents_result_dir/                      (repo: agents/agents-result/)
    page-capture/      input/page-capture_task1a2b3c4d_20260926-101530.md
                       output/page-capture_task1a2b3c4d_20260926-101534.md
                       output/page-capture_task1a2b3c4d_20260926-101534_files/capture/...
    ui-analysis/  business-analysis/  test-design/  test-automation/  test-validation/

Every file is readable Markdown (header, sources, result, summary) ending in a
`<!-- handoff-json -->` fenced JSON block holding the exact payload. The pipeline builds
each agent's input by parsing the previous agents' output files back from disk
(read_output), so the files are not a copy of what ran — they ARE what ran.

Files an output references (screenshots, evidence, the .spec.ts) are copied next to it
into `{file stem}_files/`, so each .md renders on its own.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from rag_backend.agents.handoff_render import render_handoff
from rag_backend.agents.run_layout import is_safe_relative, run_dir, write_text_atomic
from rag_backend.config import settings
from rag_backend.exceptions import AgentHandoffError

Kind = Literal["input", "output"]

JSON_MARKER = "<!-- handoff-json -->"
_JSON_FENCE = "```json\n"

STEP_AGENTS = {
    "step1_capture": "page-capture",
    "step2_ui_analysis": "ui-analysis",
    "step3_business_rules": "business-analysis",
    "step4_test_design": "test-design",
    "step5_business_confirmation": "business-analysis",
    "step6_test_automation": "test-automation",
    "step7_test_validation": "test-validation",
}
_STEP = re.compile(r"^(?P<base>step\d+_[a-z_]+?)(?:_r(?P<round>\d+))?$")


def results_root() -> Path:
    return settings.agents_result_dir


def split_step(step: str) -> tuple[str, int]:
    """("step4_test_design", 2) for "step4_test_design_r2"; round 1 has no suffix."""
    match = _STEP.match(step)
    if not match:
        return step, 1
    return match["base"], int(match["round"] or 1)


def agent_of(step: str) -> str:
    return STEP_AGENTS.get(split_step(step)[0], "agent")


def task_id(run_id: str) -> str:
    """The run id as the UI shows it (first 8 characters)."""
    return re.sub(r"[^A-Za-z0-9]", "", run_id)[:8] or "run"


def _new_rel(record: dict[str, Any], step: str, kind: Kind) -> str:
    agent = agent_of(step)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    stem = f"{agent}_task{task_id(str(record['run_id']))}_{stamp}"
    folder = f"{agent}/{kind}"
    rel = f"{folder}/{stem}.md"
    suffix = 2
    while (results_root() / rel).exists():
        rel = f"{folder}/{stem}-{suffix}.md"
        suffix += 1
    return rel


def _handoff(record: dict[str, Any], step: str) -> dict[str, Any]:
    info: dict[str, Any] = record["steps"].setdefault(step, {}).setdefault("handoff", {})
    return info


def _outputs(record: dict[str, Any], base: str) -> list[str]:
    """Output files of every executed round of a step, in execution order."""
    return [
        str(info["handoff"]["output"])
        for name, info in record.get("steps", {}).items()
        if split_step(name)[0] == base and info.get("handoff", {}).get("output")
    ]


def _output(record: dict[str, Any], step: str) -> list[str]:
    rel = record.get("steps", {}).get(step, {}).get("handoff", {}).get("output")
    return [str(rel)] if rel else []


def _round_step(base: str, design_round: int) -> str:
    return base if design_round == 1 else f"{base}_r{design_round}"


def sources_for(record: dict[str, Any], step: str) -> list[str]:
    """The earlier agents' files a step's input is built from (see pipeline.py)."""
    base, design_round = split_step(step)
    if base == "step2_ui_analysis":
        return _output(record, "step1_capture")
    if base == "step3_business_rules":
        return _output(record, "step2_ui_analysis")
    if base == "step4_test_design":
        sources = [
            *_output(record, "step3_business_rules"),
            *_output(record, "step2_ui_analysis"),
            *_output(record, "step1_capture"),
        ]
        if design_round > 1:
            previous = _round_step("step5_business_confirmation", design_round - 1)
            sources += _output(record, previous)
        return sources
    if base == "step5_business_confirmation":
        return [
            *_output(record, _round_step("step4_test_design", design_round)),
            *_output(record, "step3_business_rules"),
        ]
    if base == "step6_test_automation":
        return [
            *_outputs(record, "step4_test_design"),
            *_outputs(record, "step5_business_confirmation"),
        ]
    if base == "step7_test_validation":
        # The executed cases come from test-automation's input file.
        return [
            *_output(record, "step6_test_automation"),
            *_input(record, "step6_test_automation"),
            *_output(record, "step3_business_rules"),
            *_outputs(record, "step5_business_confirmation"),
        ]
    return []


def _input(record: dict[str, Any], step: str) -> list[str]:
    rel = record.get("steps", {}).get(step, {}).get("handoff", {}).get("input")
    return [str(rel)] if rel else []


def _artifact_refs(value: Any) -> Iterator[str]:
    """Every ArtifactRef name in a payload (dicts with name + sha256)."""
    if isinstance(value, dict):
        if isinstance(value.get("name"), str) and "sha256" in value:
            yield value["name"]
        for item in value.values():
            yield from _artifact_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _artifact_refs(item)


def _copy_attachments(record: dict[str, Any], rel: str, payload: Any) -> str | None:
    """Copy the run files an output references next to it; returns the folder (relative
    to the .md) or None when there is nothing to copy."""
    names = [name for name in _artifact_refs(payload) if is_safe_relative(name)]
    if not names:
        return None
    folder_name = f"{Path(rel).stem}_files"
    target_root = results_root() / Path(rel).parent / folder_name
    source_root = run_dir(record)
    for name in names:
        source, target = source_root / name, target_root / name
        if source.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    return folder_name


def _write(record: dict[str, Any], step: str, kind: Kind, payload: Any) -> str:
    info = _handoff(record, step)
    rel = str(info.get(kind) or _new_rel(record, step, kind))
    info[kind] = rel
    files = _copy_attachments(record, rel, payload) if kind == "output" else None
    if files:
        info["files"] = f"{Path(rel).parent.as_posix()}/{files}"
    body = render_handoff(
        record,
        step,
        split_step(step)[0],
        kind,
        payload,
        rel,
        files,
        agent_of(step),
        task_id(str(record["run_id"])),
    )
    block = json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    write_text_atomic(results_root() / rel, f"{body}\n{JSON_MARKER}\n{_JSON_FENCE}{block}\n```\n")
    return rel


def write_input(record: dict[str, Any], step: str, payload: Any) -> str:
    """Write the step's input file; records its sources (computed from the run so far)."""
    _handoff(record, step)["sources"] = sources_for(record, step)
    return _write(record, step, "input", payload)


def write_output(record: dict[str, Any], step: str) -> str:
    """Write (or rewrite, keeping its name) the step's output file from the record: the
    output payload, result status, checks, model calls and error."""
    return _write(record, step, "output", record["steps"].get(step, {}).get("output"))


def resolve(rel: str) -> Path | None:
    """The handoff file for a results-relative path; None when unsafe or missing."""
    if not is_safe_relative(rel):
        return None
    root = results_root().resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def parse_payload(text: str) -> Any:
    start = text.rfind(JSON_MARKER)
    if start < 0:
        raise AgentHandoffError("no handoff JSON block")
    fence = text.find(_JSON_FENCE, start)
    if fence < 0:
        raise AgentHandoffError("handoff JSON block is not fenced")
    body_start = fence + len(_JSON_FENCE)
    # json.dumps never emits a raw newline inside a string, so the first "\n```" after
    # the opening fence is the closing one.
    end = text.find("\n```", body_start)
    try:
        return json.loads(text[body_start : end if end >= 0 else None])
    except json.JSONDecodeError as error:
        raise AgentHandoffError(f"handoff JSON block is invalid: {error}") from error


def read_file[ModelT: BaseModel](rel: str, model: type[ModelT]) -> ModelT:
    path = resolve(rel)
    if path is None:
        raise AgentHandoffError(f"handoff file not found: {rel}")
    try:
        return model.model_validate(parse_payload(path.read_text(encoding="utf-8")))
    except AgentHandoffError as error:
        raise AgentHandoffError(f"{rel}: {error}") from error
    except ValidationError as error:
        raise AgentHandoffError(f"{rel}: not a valid {model.__name__}: {error}") from error


def _path_of(record: dict[str, Any], step: str, kind: Kind) -> str:
    rel = record.get("steps", {}).get(step, {}).get("handoff", {}).get(kind)
    if not rel:
        raise AgentHandoffError(f"{step} has no {kind} file")
    return str(rel)


def read_output[ModelT: BaseModel](
    record: dict[str, Any], step: str, model: type[ModelT]
) -> ModelT:
    """The step's output, parsed back from its handoff file."""
    return read_file(_path_of(record, step, "output"), model)


def read_input[ModelT: BaseModel](record: dict[str, Any], step: str, model: type[ModelT]) -> ModelT:
    return read_file(_path_of(record, step, "input"), model)


def listed_paths(record: dict[str, Any]) -> set[str]:
    """Every handoff file (and attachment folder) of a run — what the API may serve."""
    paths: set[str] = set()
    for info in record.get("steps", {}).values():
        handoff = info.get("handoff", {})
        paths.update(str(handoff[key]) for key in ("input", "output", "files") if key in handoff)
    return paths
