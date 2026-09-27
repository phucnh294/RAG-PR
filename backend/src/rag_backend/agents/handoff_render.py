"""Markdown bodies of the per-agent handoff files (handoff.py): header, sources, result
line, a readable summary of the payload, checks and model calls. The exact payload is
appended by handoff.py as a JSON block; everything here is for people reading the file."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_PASSED = "✅"
_FAILED = "❌"
_SKIPPED = "⏭"


def cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _link(rel: str) -> str:
    """Link from a handoff file ({agent}/{kind}/x.md) to another results-relative path."""
    return f"[{rel}](../../{rel})"


def target(locator: dict[str, Any] | None) -> str:
    if not locator:
        return "—"
    text = f"{locator.get('strategy')}={locator.get('value')}"
    return f"{text} (name={locator['name']})" if locator.get("name") else text


def _icon(status: str | None) -> str:
    return {"passed": _PASSED, "failed": _FAILED, "error": _FAILED}.get(str(status), _SKIPPED)


# --- result line ---


def _outcome(step: str, payload: Any) -> str:
    """One line saying what the agent produced."""
    if not isinstance(payload, dict):
        return "no output"
    if step.startswith("step1_"):
        return (
            f"page {payload.get('title')!r} loaded at {payload.get('final_url')}, "
            f"{len(payload.get('elements', []))} element(s) captured"
        )
    if step.startswith("step2_"):
        return (
            f"{len(payload.get('elements', []))} UI element(s), "
            f"{len(payload.get('messages', []))} message(s) identified"
        )
    if step.startswith("step3_"):
        return f"{len(payload.get('rules', []))} business rule(s) extracted"
    if step.startswith("step4_"):
        return f"{len(payload.get('cases', []))} test case(s) designed"
    if step.startswith("step5_"):
        verdicts = payload.get("verdicts", [])
        approved = sum(v.get("verdict") == "approved" for v in verdicts)
        uncovered = payload.get("uncovered_rule_ids", [])
        text = f"{approved} approved, {len(verdicts) - approved} rejected"
        return text + (f", uncovered rules: {', '.join(uncovered)}" if uncovered else "")
    if step.startswith("step6_"):
        results = payload.get("results", [])
        passed = sum(r.get("status") == "passed" for r in results)
        return f"{passed}/{len(results)} test case(s) passed"
    if step.startswith("step7_"):
        return (
            f"{payload.get('passed')}/{payload.get('total')} passed "
            f"({round(float(payload.get('pass_rate', 0)) * 100)}%), "
            f"{len(payload.get('rules_verified', []))}/{len(payload.get('rule_coverage', {}))} "
            "rule(s) verified"
        )
    return "done"


def _result_line(info: dict[str, Any], step: str, payload: Any) -> str:
    status = info.get("status")
    if status == "failed":
        return f"## Result: {_FAILED} FAILED — {cell(info.get('error'))}"
    if status != "succeeded":
        return f"## Result: ⏳ {str(status).upper()}"
    flagged = [c["name"] for c in info.get("checks", []) if not c.get("passed")]
    warn = f" · ⚠ {len(flagged)} check(s) flagged: {', '.join(flagged)}" if flagged else ""
    return f"## Result: {_PASSED} SUCCESS — {_outcome(step, payload)}{warn}"


# --- per-step summaries ---


def _capture(payload: dict[str, Any], files: str | None, _: dict[str, Any]) -> list[str]:
    lines = []
    shot = payload.get("screenshot") or {}
    if files and shot.get("name"):
        lines += [f"![Page screenshot]({files}/{shot['name']})", ""]
    lines += [
        "## Captured elements",
        "",
        "| Tag | Id | Label / text | Role | Required | Visible | Suggested locator |",
        "|---|---|---|---|---|---|---|",
    ]
    for element in payload.get("elements", []):
        lines.append(
            f"| {cell(element.get('tag'))} | {cell(element.get('id'))} "
            f"| {cell(element.get('label') or element.get('text'))} | {cell(element.get('role'))} "
            f"| {'yes' if element.get('required') else ''} "
            f"| {'yes' if element.get('visible', True) else 'hidden'} "
            f"| {cell(target(element.get('suggested_locator')))} |"
        )
    return lines


def _ui(payload: dict[str, Any], _files: str | None, _: dict[str, Any]) -> list[str]:
    lines = [
        f"**Page:** {cell(payload.get('page_title'))} — {cell(payload.get('purpose'))}",
        "",
        "## UI elements",
        "",
        "| Element | Type | Label | Required | Locator | Source |",
        "|---|---|---|---|---|---|",
    ]
    for element in payload.get("elements", []):
        lines.append(
            f"| {cell(element.get('element_id'))} | {cell(element.get('type'))} "
            f"| {cell(element.get('label'))} | {'yes' if element.get('required') else ''} "
            f"| {cell(target(element.get('locator')))} | {cell(element.get('source'))} |"
        )
    for title, key in (("Messages", "messages"), ("Uncertainties", "uncertainties")):
        if payload.get(key):
            lines += ["", f"## {title}", "", *[f"- {item}" for item in payload[key]]]
    return lines


def _rules_table(rules: list[dict[str, Any]]) -> list[str]:
    lines = ["| Rule | Type | Field | Title | Source quote |", "|---|---|---|---|---|"]
    for rule in rules:
        lines.append(
            f"| {cell(rule.get('rule_id'))} | {cell(rule.get('type'))} "
            f"| {cell(rule.get('field'))} | {cell(rule.get('title'))} "
            f"| {cell(rule.get('source_quote'))} |"
        )
    return lines


def _rules(payload: dict[str, Any], _files: str | None, _: dict[str, Any]) -> list[str]:
    return ["## Business rules", "", *_rules_table(payload.get("rules", []))]


def _cases_table(cases: list[dict[str, Any]]) -> list[str]:
    lines = ["| Case | Title | Type | Rules | Steps | Expected |", "|---|---|---|---|---|---|"]
    for case in cases:
        lines.append(
            f"| {cell(case.get('case_id'))} | {cell(case.get('title'))} "
            f"| {cell(case.get('type'))} | {cell(', '.join(case.get('source_rule_ids', [])))} "
            f"| {len(case.get('steps', []))} | {cell(case.get('expected'))} |"
        )
    return lines


def _case_steps(case: dict[str, Any]) -> list[str]:
    return [
        f"{index}. `{step.get('action')}` {target(step.get('locator'))}"
        + (f" — `{step.get('value')}`" if step.get("value") else "")
        for index, step in enumerate(case.get("steps", []), start=1)
    ]


def _design(payload: dict[str, Any], _files: str | None, _: dict[str, Any]) -> list[str]:
    lines = ["## Test cases", "", *_cases_table(payload.get("cases", []))]
    for case in payload.get("cases", []):
        lines += ["", f"### {case.get('case_id')} — {case.get('title')}", "", *_case_steps(case)]
    return lines


def _verdicts(payload: dict[str, Any], _files: str | None, _: dict[str, Any]) -> list[str]:
    lines = ["## Verdicts", "", "| Case | Verdict | Reason |", "|---|---|---|"]
    for verdict in payload.get("verdicts", []):
        icon = _PASSED if verdict.get("verdict") == "approved" else _FAILED
        lines.append(
            f"| {cell(verdict.get('case_id'))} | {icon} {verdict.get('verdict')} "
            f"| {cell(verdict.get('reason'))} |"
        )
    uncovered = payload.get("uncovered_rule_ids", [])
    lines += ["", f"**Uncovered rules:** {', '.join(uncovered) if uncovered else 'none'}"]
    return lines


def step_rows(steps: list[dict[str, Any]], evidence_prefix: str | None) -> list[str]:
    """Per test step: what ran, passed/failed, the message the page showed, evidence."""
    lines = [
        (
            "| # | Action | Target | Value | Result | Message shown on page | Observed | Error "
            "| Evidence |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for step in steps:
        evidence = step.get("evidence") or {}
        link = (
            f"[screenshot]({evidence_prefix}/{evidence['name']})"
            if evidence_prefix and evidence.get("name")
            else "—"
        )
        messages = "<br>".join(cell(m) for m in step.get("page_messages", [])) or "—"
        lines.append(
            f"| {int(step.get('index', 0)) + 1} | {cell(step.get('action'))} "
            f"| {cell(target(step.get('locator')))} | {cell(step.get('value'))} "
            f"| {_icon(step.get('status'))} {step.get('status')} | {messages} "
            f"| {cell(step.get('observed'))} | {cell(step.get('error'))} | {link} |"
        )
    return lines


def _automation(payload: dict[str, Any], files: str | None, _: dict[str, Any]) -> list[str]:
    lines = [f"**Base URL:** {payload.get('base_url')}"]
    spec = payload.get("spec_ts") or {}
    if files and spec.get("name"):
        lines.append(f"**Generated spec:** [{spec['name']}]({files}/{spec['name']})")
    if payload.get("not_automated_case_ids"):
        lines.append(f"**Not automated:** {', '.join(payload['not_automated_case_ids'])}")
    for result in payload.get("results", []):
        seconds = float(result.get("duration_ms", 0)) / 1000
        lines += [
            "",
            (
                f"## {_icon(result.get('status'))} {result.get('case_id')} — "
                f"{str(result.get('status')).upper()} in {seconds:.1f}s"
            ),
            "",
            *step_rows(result.get("steps", []), files),
        ]
        if result.get("console_errors"):
            lines += ["", "Console errors:", *[f"- `{e}`" for e in result["console_errors"]]]
        shots = [s for s in result.get("steps", []) if (s.get("evidence") or {}).get("name")]
        if files and shots:
            lines += ["", "### Evidence"]
            for step in shots:
                name = step["evidence"]["name"]
                lines += [
                    "",
                    (
                        f"**Step {int(step['index']) + 1} · {step.get('action')} · "
                        f"{_icon(step.get('status'))} {step.get('status')}**"
                    ),
                    "",
                    f"![Step {int(step['index']) + 1}]({files}/{name})",
                ]
    return lines


def _validation(payload: dict[str, Any], _files: str | None, record: dict[str, Any]) -> list[str]:
    automation = record.get("steps", {}).get("step6_test_automation", {})
    evidence_folder = automation.get("handoff", {}).get("files")
    prefix = f"../../{evidence_folder}" if evidence_folder else None
    results = {r["case_id"]: r for r in (automation.get("output") or {}).get("results", [])}
    analysis = {a["case_id"]: a for a in payload.get("failure_analysis", [])}
    lines = [str(payload.get("summary") or ""), "", "## Test cases", ""]
    for case in payload.get("cases", []):
        status = case.get("status")
        lines.append(
            f"- {_icon(status)} **{case.get('case_id')}** {case.get('title')} — "
            f"{str(status).upper()} (rules: {', '.join(case.get('source_rule_ids', [])) or '—'})"
        )
        steps = results.get(case.get("case_id"), {}).get("steps", [])
        failing = next((s for s in steps if s.get("status") == "failed"), None)
        if failing is not None:
            shown = "; ".join(failing.get("page_messages", [])) or "no message"
            lines += [
                (
                    f"  - Failed at step {int(failing['index']) + 1} `{failing.get('action')}` "
                    f"{target(failing.get('locator'))}, expected `{failing.get('value')}`"
                ),
                f"  - Page showed: {shown} · observed: {failing.get('observed') or '—'}",
                f"  - Error: {cell(failing.get('error'))}",
            ]
        elif steps:
            shown = "; ".join(steps[-1].get("page_messages", [])) or "no message"
            lines.append(f"  - Page showed at the end: {shown}")
        cause = analysis.get(case.get("case_id"))
        if cause:
            lines.append(
                f"  - Suspected cause: **{cause['suspected_cause']}** — {cause['explanation']}"
            )
        # The proof: the failing step's screenshot, or the last step's for a passed case.
        proof = failing or next((s for s in reversed(steps) if s.get("evidence")), None)
        name = ((proof or {}).get("evidence") or {}).get("name")
        if prefix and proof and name:
            label = f"Step {int(proof['index']) + 1} · {proof.get('action')}"
            lines += ["", f"  ![{case.get('case_id')} — {label}]({prefix}/{name})", ""]
    lines += ["", "## Rule coverage", "", "| Rule | Covered by | Verified |", "|---|---|---|"]
    verified = set(payload.get("rules_verified", []))
    for rule, cases in payload.get("rule_coverage", {}).items():
        lines.append(
            f"| {rule} | {', '.join(cases) or 'not covered'} "
            f"| {_PASSED if rule in verified else _FAILED} |"
        )
    dropped = payload.get("dropped_cases", [])
    if dropped:
        lines += ["", "## Rejected by the business agent (not executed)", ""]
        lines += [f"- {d['case_id']} {d['title']} — {d['reason']}" for d in dropped]
    return lines


_OUTPUT_RENDERERS: dict[str, Callable[[dict[str, Any], str | None, dict[str, Any]], list[str]]] = {
    "step1_capture": _capture,
    "step2_ui_analysis": _ui,
    "step3_business_rules": _rules,
    "step4_test_design": _design,
    "step5_business_confirmation": _verdicts,
    "step6_test_automation": _automation,
    "step7_test_validation": _validation,
}


def _input_summary(base: str, payload: dict[str, Any]) -> list[str]:
    if base == "step1_capture":
        return [f"**Target URL:** {payload.get('target_url')}"]
    if base == "step2_ui_analysis":
        return [
            f"**Page:** {payload.get('page_title')} — {payload.get('page_url')}",
            (
                f"**DOM elements:** {len(payload.get('dom_elements', []))} · "
                f"**Screenshot:** `{(payload.get('image') or {}).get('name')}` (sent as an image)"
            ),
        ]
    if base == "step3_business_rules":
        requirement = str(payload.get("requirement", ""))
        quoted = "\n".join(f"> {line}" for line in requirement.splitlines())
        elements = len((payload.get("ui_analysis") or {}).get("elements", []))
        return ["## Requirement text", "", quoted, "", f"**UI analysis:** {elements} element(s)"]
    if base == "step4_test_design":
        lines = [
            f"**Round:** {payload.get('round')}",
            "",
            "## Business rules",
            "",
            *_rules_table((payload.get("rules") or {}).get("rules", [])),
        ]
        feedback = payload.get("feedback")
        if feedback:
            lines += ["", "## Business feedback from the previous round", ""]
            lines += [
                f"- {_FAILED} {item['case']['case_id']} rejected: {item['reason']}"
                for item in feedback.get("rejected_cases", [])
            ]
            uncovered = feedback.get("uncovered_rule_ids", [])
            lines.append(f"- Uncovered rules: {', '.join(uncovered) if uncovered else 'none'}")
        return lines
    if base == "step5_business_confirmation":
        return [
            f"**Round:** {payload.get('round')}",
            "",
            "## Cases to review",
            "",
            *_cases_table(payload.get("cases", [])),
        ]
    if base == "step6_test_automation":
        return [
            f"**Base URL:** {payload.get('base_url')}",
            "",
            "## Approved cases to execute",
            "",
            *_cases_table(payload.get("approved_cases", [])),
        ]
    if base == "step7_test_validation":
        lines = ["## Execution results", ""]
        for result in payload.get("results", []):
            lines.append(f"- {_icon(result.get('status'))} {result.get('case_id')}")
        return lines
    return []


def _checks(info: dict[str, Any]) -> list[str]:
    checks = info.get("checks", [])
    if not checks:
        return []
    lines = [
        "## Contract checks",
        "",
        "| Check | Severity | Result | Detail |",
        "|---|---|---|---|",
    ]
    for item in checks:
        lines.append(
            f"| {cell(item.get('name'))} | {cell(item.get('severity'))} "
            f"| {_PASSED if item.get('passed') else _FAILED} | {cell(item.get('detail'))} |"
        )
    return lines


def _calls(info: dict[str, Any]) -> list[str]:
    calls = info.get("llm_calls", [])
    if not calls:
        return []
    lines = [
        "## Model calls",
        "",
        "Full prompts and raw responses are in the run's `run.json`.",
        "",
        "| Attempt | Try | Model | Duration | Outcome |",
        "|---|---|---|---|---|",
    ]
    for call in calls:
        if call.get("error"):
            outcome = f"{_FAILED} {call['error']}"
        elif call.get("valid"):
            outcome = f"{_PASSED} valid"
        else:
            outcome = f"{_FAILED} {call.get('parse_error') or 'schema validation failed'}"
        duration = call.get("duration_ms")
        lines.append(
            f"| {call.get('attempt')} | {call.get('transport_try', 1)} "
            f"| {cell(call.get('provider'))}/{cell(call.get('model'))} "
            f"| {f'{float(duration) / 1000:.1f}s' if duration is not None else '—'} "
            f"| {cell(outcome)} |"
        )
    return lines


def render_handoff(
    record: dict[str, Any],
    step: str,
    base: str,
    kind: str,
    payload: Any,
    rel: str,
    files: str | None,
    agent: str,
    task: str,
) -> str:
    """`base` is the step without its round suffix ("step4_test_design" for _r2)."""
    info = record.get("steps", {}).get(step, {})
    handoff = info.get("handoff", {})
    lines = [
        f"# {agent} · {kind} · task{task}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Agent | {agent} |",
        f"| Pipeline step | `{step}` |",
        f"| Run id | `{record.get('run_id')}` |",
        f"| Task | task{task} |",
        f"| File | `{rel}` |",
        f"| Status | {cell(info.get('status'))} |",
        f"| Time | {cell(info.get(f'{kind}_at') or info.get('failed_at'))} |",
    ]
    if kind == "output" and info.get("duration_ms") is not None:
        lines.append(f"| Duration | {float(info['duration_ms']) / 1000:.1f}s |")
    lines.append("")
    if kind == "input":
        sources = handoff.get("sources", [])
        lines += ["## Sources", ""]
        if sources:
            lines.append("Built by parsing these files of the previous agents:")
            lines += [f"- {_link(source)}" for source in sources]
        else:
            lines.append("First agent of the chain: built from the run request.")
        lines.append("")
        if isinstance(payload, dict):
            lines += [*_input_summary(base, payload), ""]
    else:
        if handoff.get("input"):
            lines += [f"**Input:** {_link(str(handoff['input']))}", ""]
        lines += [_result_line(info, step, payload), ""]
        renderer = _OUTPUT_RENDERERS.get(base)
        if renderer and isinstance(payload, dict):
            lines += [*renderer(payload, files, record), ""]
        for section in (_checks(info), _calls(info)):
            if section:
                lines += [*section, ""]
    lines += ["## Payload", "", "The exact data, parsed by the next agent:", ""]
    return "\n".join(lines)
