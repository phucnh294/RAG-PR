"""Step 7: test validation — metrics and rule coverage computed by code, then the
validation agent explains the result and classifies each failure."""

from __future__ import annotations

from typing import Any

from rag_backend.agents import clients
from rag_backend.agents.checks import check
from rag_backend.agents.llm_json import call_structured, prompt_json
from rag_backend.agents.prompts import TEST_VALIDATION_SYSTEM
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import (
    AutomationResult,
    BusinessRules,
    CaseReport,
    CaseRunResult,
    DroppedCase,
    TestCase,
    ValidationNarrative,
    ValidationReport,
)

STEP = "step7_test_validation"


def _case_reports(cases: list[TestCase], automation: AutomationResult) -> list[CaseReport]:
    results = {result.case_id: result for result in automation.results}
    reports = []
    for case in cases:
        result = results.get(case.case_id)
        failed_step = None
        error = None
        if result is not None:
            failing = next((s for s in result.steps if s.status == "failed"), None)
            if failing is not None:
                failed_step, error = failing.index, failing.error
        reports.append(
            CaseReport(
                case_id=case.case_id,
                title=case.title,
                status=result.status if result is not None else "not_run",
                source_rule_ids=case.source_rule_ids,
                failed_step=failed_step,
                error=error,
            )
        )
    return reports


def _result_summary(result: CaseRunResult) -> dict[str, Any]:
    """What the validation agent needs to explain a result: the status and, for a failure,
    the failing step with its error and what the page actually showed. Passing steps and
    evidence file references are left out — they only cost prompt tokens (on CPU the full
    results made the local model run out of output budget)."""
    failed = next((step for step in result.steps if step.status == "failed"), None)
    summary: dict[str, Any] = {"case_id": result.case_id, "status": result.status}
    if failed is not None:
        summary["failed_step"] = failed.model_dump(
            mode="json", include={"index", "action", "locator", "value", "error", "observed"}
        )
    if result.console_errors:
        summary["console_errors"] = result.console_errors
    return summary


def compute_report(
    rules: BusinessRules,
    cases: list[TestCase],
    dropped: list[DroppedCase],
    automation: AutomationResult,
) -> ValidationReport:
    """Every number in the report comes from here, never from the LLM."""
    reports = _case_reports(cases, automation)
    executed = [r for r in reports if r.status != "not_run"]
    passed = sum(r.status == "passed" for r in executed)
    coverage: dict[str, list[str]] = {rule.rule_id: [] for rule in rules.rules}
    verified: set[str] = set()
    for report in executed:
        for rule_id in report.source_rule_ids:
            if rule_id in coverage:
                coverage[rule_id].append(report.case_id)
                if report.status == "passed":
                    verified.add(rule_id)
    return ValidationReport(
        total=len(executed),
        passed=passed,
        failed=sum(r.status == "failed" for r in executed),
        errored=sum(r.status == "error" for r in executed),
        pass_rate=round(passed / len(executed), 3) if executed else 0.0,
        cases=reports,
        rule_coverage=coverage,
        rules_verified=sorted(verified),
        uncovered_rules=sorted(rule_id for rule_id, ids in coverage.items() if not ids),
        dropped_cases=dropped,
        summary="",
        failure_analysis=[],
    )


async def run(
    ctx: AgentContext,
    rules: BusinessRules,
    cases: list[TestCase],
    dropped: list[DroppedCase],
    automation: AutomationResult,
) -> ValidationReport:
    report = compute_report(rules, cases, dropped, automation)
    agent_input = {
        "rules": rules.model_dump(mode="json"),
        "cases": [case.model_dump(mode="json") for case in cases],
        "results": [_result_summary(result) for result in automation.results],
        "metrics": report.model_dump(mode="json", exclude={"summary", "failure_analysis"}),
    }
    ctx.begin(STEP, agent_input)
    messages = [
        {"role": "system", "content": TEST_VALIDATION_SYSTEM},
        {
            "role": "user",
            "content": f"Validation input (JSON):\n{prompt_json(agent_input)}",
        },
    ]
    narrative = await call_structured(
        ctx, STEP, clients.agents_text_client, messages, ValidationNarrative
    )
    failing_ids = {c.case_id for c in report.cases if c.status in ("failed", "error")}
    analysed = [a for a in narrative.failure_analysis if a.case_id in failing_ids]
    invented = sorted({a.case_id for a in narrative.failure_analysis} - failing_ids)
    unexplained = sorted(failing_ids - {a.case_id for a in analysed})
    report = report.model_copy(update={"summary": narrative.summary, "failure_analysis": analysed})
    checks = [
        check(
            "counts_add_up",
            report.passed + report.failed + report.errored == report.total,
            f"{report.passed}+{report.failed}+{report.errored} of {report.total}",
            "error",
        ),
        check(
            "no_invented_failures",
            not invented,
            f"analysis for non-failing cases dropped: {', '.join(invented)}" if invented else "",
        ),
        check(
            "every_failure_explained",
            not unexplained,
            (
                f"no analysis for: {', '.join(unexplained)}"
                if unexplained
                else "every failed case has a suspected cause"
            ),
        ),
    ]
    ctx.finish(STEP, report.model_dump(mode="json"), [c.model_dump() for c in checks])
    return report
