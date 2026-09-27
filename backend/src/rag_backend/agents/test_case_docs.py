"""One folder per test case: test-case.md (human-readable) + result.json (raw result) +
evidence/ (screenshots saved by step 6). Layout: run_layout.py.

The Markdown is rewritten as the case moves through the pipeline: designed (step 4) ->
approved/rejected by the business agent (step 5) -> executed with evidence (step 6) ->
failure analysis (step 7), so at any moment it shows everything known about the case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rag_backend.agents.run_layout import case_folder, write_json_atomic, write_text_atomic
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import (
    BusinessRules,
    CaseRunResult,
    CaseVerdict,
    FailureAnalysis,
    Locator,
    TestCase,
)

_RESULT_ICON = {"passed": "✅ PASSED", "failed": "❌ FAILED", "error": "⚠️ ERROR"}
_ICONS = {"passed": "✅", "failed": "❌", "skipped": "⏭"}


@dataclass
class CaseEntry:
    case: TestCase
    verdict: CaseVerdict | None = None
    design_round: int = 1
    result: CaseRunResult | None = None
    analysis: FailureAnalysis | None = None


@dataclass
class CaseLedger:
    """Everything known about every designed test case, written to its folder."""

    ctx: AgentContext
    rules: BusinessRules
    entries: dict[str, CaseEntry] = field(default_factory=dict)

    def add_design(self, case: TestCase, design_round: int) -> None:
        self.entries[case.case_id] = CaseEntry(case=case, design_round=design_round)

    def set_verdict(self, verdict: CaseVerdict) -> None:
        if verdict.case_id in self.entries:
            self.entries[verdict.case_id].verdict = verdict

    def set_result(self, result: CaseRunResult) -> None:
        if result.case_id in self.entries:
            self.entries[result.case_id].result = result

    def set_analysis(self, analysis: FailureAnalysis) -> None:
        if analysis.case_id in self.entries:
            self.entries[analysis.case_id].analysis = analysis

    def write(self) -> None:
        summaries = []
        for entry in self.entries.values():
            folder = case_folder(entry.case.case_id)
            root = self.ctx.root / folder
            write_text_atomic(
                root / "test-case.md", render_case(entry, self.rules, self.ctx.run_id)
            )
            if entry.result is not None:
                write_json_atomic(root / "result.json", entry.result.model_dump(mode="json"))
            summaries.append(
                {
                    "case_id": entry.case.case_id,
                    "title": entry.case.title,
                    "folder": folder,
                    "verdict": entry.verdict.verdict if entry.verdict else None,
                    "result": entry.result.status if entry.result else None,
                    "evidence_count": (
                        sum(step.evidence is not None for step in entry.result.steps)
                        if entry.result
                        else 0
                    ),
                }
            )
        self.ctx.record["test_cases"] = summaries
        self.ctx.persist()


def _md(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ") if value not in (None, "") else "—"


def _locator(locator: Locator | None) -> str:
    if locator is None:
        return "—"
    if locator.strategy == "role":
        name = f' name="{locator.name}"' if locator.name else ""
        return f"`role={locator.value}{name}`"
    return f'`{locator.strategy}="{locator.value}"`'


def _evidence_link(name: str) -> str:
    # Links are relative to test-case.md, which sits in the case folder.
    relative = name.split("/", 2)[-1]
    return f"[screenshot]({relative})"


def render_case(entry: CaseEntry, rules: BusinessRules, run_id: str) -> str:
    case, result, verdict = entry.case, entry.result, entry.verdict
    rule_titles = {rule.rule_id: rule for rule in rules.rules}
    status = _RESULT_ICON.get(result.status, result.status) if result else "not executed"
    lines = [
        f"# {case.case_id} — {case.title}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Run | `{run_id}` |",
        f"| Priority / type | {case.priority} / {case.type} |",
        f"| Designed in round | {entry.design_round} |",
        f"| Business verdict | {_md(verdict.verdict if verdict else 'pending')} |",
        f"| Result | {status}" + (f" in {result.duration_ms / 1000:.1f}s" if result else "") + " |",
        "",
        "## Business rules covered",
        "",
    ]
    for rule_id in case.source_rule_ids:
        rule = rule_titles.get(rule_id)
        lines.append(
            f"- **{rule_id}** — {rule.title}: {rule.description}"
            if rule
            else f"- **{rule_id}** — (not an extracted rule)"
        )
    if verdict:
        lines += ["", "## Business confirmation", "", f"**{verdict.verdict}** — {verdict.reason}"]
    lines += ["", "## Preconditions", "", _md(case.preconditions), "", "## Test data", ""]
    if case.test_data:
        lines += ["| Field | Value |", "|---|---|"]
        lines += [f"| {_md(key)} | `{_md(value)}` |" for key, value in case.test_data.items()]
    else:
        lines.append("—")

    step_results = {step.index: step for step in result.steps} if result else {}
    lines += [
        "",
        "## Steps and evidence",
        "",
        "| # | Action | Target | Value | Result | Message shown on page | Observed | Evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for index, step in enumerate(case.steps):
        ran = step_results.get(index)
        outcome: str = f"{_ICONS.get(ran.status, '')} {ran.status}".strip() if ran else "not run"
        shown = "<br>".join(_md(m) for m in ran.page_messages) if ran and ran.page_messages else "—"
        if ran and ran.error:
            outcome += f": {_md(ran.error)[:200]}"
        lines.append(
            f"| {index + 1} | {step.action} | {_locator(step.locator)} "
            f"| {_md(step.value if step.value is not None else None)} | {outcome} | {shown} "
            f"| {_md(ran.observed if ran else None)} "
            f"| {_evidence_link(ran.evidence.name) if ran and ran.evidence else '—'} |"
        )

    lines += ["", "## Expected result", "", _md(case.expected), "", "## Actual result", ""]
    if result is None:
        lines.append(
            "Not executed"
            + (
                " — rejected by the business agent."
                if verdict and verdict.verdict == "rejected"
                else "."
            )
        )
    elif result.status == "passed":
        lines.append(f"All {len(result.steps)} steps passed; see the evidence column.")
    else:
        failed = next((step for step in result.steps if step.status == "failed"), None)
        if failed is not None:
            lines.append(
                f"Step {failed.index + 1} ({failed.action}) failed: {_md(failed.error)}. "
                f"Observed: {_md(failed.observed)}. Page showed: "
                f"{'; '.join(failed.page_messages) or 'no message'}."
            )
        else:
            lines.append(f"Case ended with status {result.status}.")
        if result.failure_screenshot:
            lines += [
                "",
                f"![Failure screenshot]({result.failure_screenshot.name.split('/', 2)[-1]})",
            ]
    if entry.analysis:
        lines += [
            "",
            "## Failure analysis (test validation agent)",
            "",
            f"**{entry.analysis.suspected_cause}** — {entry.analysis.explanation}",
        ]
    if result and result.console_errors:
        lines += ["", "## Browser console errors", ""]
        lines += [f"- `{_md(error)}`" for error in result.console_errors]
    lines.append("")
    return "\n".join(lines)
