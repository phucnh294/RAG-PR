"""The run folder's README (layout: run_layout.py): a summary of the run with every
agent's input/output handoff file (handoff.py) and every test case. Rewritten on every
persist, so it follows a run in progress."""

from __future__ import annotations

from typing import Any

from rag_backend.agents.run_layout import run_dir, write_text_atomic


def write_run_files(record: dict[str, Any]) -> None:
    write_text_atomic(run_dir(record) / "README.md", render_readme(record))


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ") if value is not None else "—"


def _path(rel: Any) -> str:
    return f"`{rel}`" if rel else "—"


def _seconds(duration_ms: Any) -> str:
    return f"{float(duration_ms) / 1000:.1f}s" if duration_ms is not None else "—"


def render_readme(record: dict[str, Any]) -> str:
    models = record.get("models", {})
    lines = [
        f"# Agents run {record['run_id']}",
        "",
        f"- **Status:** {record.get('status')}",
        f"- **Target:** {record.get('target_url')}",
        f"- **Started by:** {record.get('created_by_username')}",
        f"- **Started / finished:** {record.get('started_at')} / {record.get('finished_at')}",
        "- **Models:** "
        + ", ".join(f"{role} = {m.get('provider')}/{m.get('model')}" for role, m in models.items()),
    ]
    if record.get("error"):
        lines.append(f"- **Error:** {record['error']}")
    lines += [
        "",
        "## Agent steps",
        "",
        (
            "Each agent's input and output are Markdown files under the agents result folder "
            "(`agents/agents-result/` in the repo); each output file is parsed to build the "
            "next agent's input. Full model prompts and responses are in `run.json`."
        ),
        "",
        "| # | Step | Status | Duration | Checks flagged | Input | Output |",
        "|---|---|---|---|---|---|---|",
    ]
    for index, (name, step) in enumerate(record.get("steps", {}).items(), start=1):
        checks = step.get("checks", [])
        flagged = [c["name"] for c in checks if not c.get("passed")]
        files = step.get("handoff", {})
        lines.append(
            f"| {index} | {name} | {step.get('status')} | {_seconds(step.get('duration_ms'))} "
            f"| {_cell(', '.join(flagged) or ('none' if checks else '—'))} "
            f"| {_path(files.get('input'))} | {_path(files.get('output'))} |"
        )
    cases = record.get("test_cases", [])
    if cases:
        lines += [
            "",
            "## Test cases",
            "",
            "| Case | Title | Business verdict | Result | Evidence |",
            "|---|---|---|---|---|",
        ]
        for case in cases:
            lines.append(
                f"| [{case['case_id']}]({case['folder']}/test-case.md) | {_cell(case['title'])} "
                f"| {_cell(case.get('verdict'))} | {_cell(case.get('result') or 'not run')} "
                f"| {case.get('evidence_count', 0)} screenshot(s) |"
            )
    report = record.get("report")
    if report:
        lines += [
            "",
            "## Validation report",
            "",
            (
                f"{report.get('passed')}/{report.get('total')} passed "
                f"({round(float(report.get('pass_rate', 0)) * 100)}%), rules verified: "
                f"{', '.join(report.get('rules_verified', [])) or 'none'}."
            ),
            "",
            str(report.get("summary", "")),
        ]
    lines.append("")
    return "\n".join(lines)
