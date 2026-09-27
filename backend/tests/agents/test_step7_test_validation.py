from __future__ import annotations

import pytest

from rag_backend.agents import runner_client, step6_test_automation, step7_test_validation
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import BusinessRules, DroppedCase, TestCase
from tests.agents.conftest import AgentFakes
from tests.agents.fakes import (
    TARGET_URL,
    FakeRunnerClient,
    email_case,
    first_name_case,
    narrative_json,
    rules_json,
    success_case,
)


async def test_report_numbers_come_from_results_and_analysis_is_filtered(
    ctx: AgentContext, fakes: AgentFakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_client, "test_runner_client", FakeRunnerClient(fail={"TC-REG-002"}))
    rules = BusinessRules.model_validate_json(rules_json())
    cases = [TestCase.model_validate(c) for c in (success_case(), first_name_case())]
    dropped = [DroppedCase(case_id="TC-REG-003", title="Email", reason="wrong text")]
    automation = await step6_test_automation.run(ctx, cases, TARGET_URL, "Register Account")
    # The agent explains the real failure and invents one for a passing case.
    fakes.text._responses = [
        narrative_json({"TC-REG-002": "app_defect", "TC-REG-001": "test_defect"})
    ]

    report = await step7_test_validation.run(ctx, rules, cases, dropped, automation)

    assert (report.total, report.passed, report.failed, report.pass_rate) == (2, 1, 1, 0.5)
    assert report.rule_coverage == {
        "BR-001": ["TC-REG-002"],
        "BR-002": [],
        "BR-003": ["TC-REG-001"],
    }
    assert report.rules_verified == ["BR-003"]
    assert report.uncovered_rules == ["BR-002"]
    assert [d.case_id for d in report.dropped_cases] == ["TC-REG-003"]
    assert [a.case_id for a in report.failure_analysis] == ["TC-REG-002"]
    step = ctx.record["steps"]["step7_test_validation"]
    assert step["input"]["metrics"]["failed"] == 1
    checks = {c["name"]: c["passed"] for c in step["checks"]}
    assert checks == {
        "counts_add_up": True,
        "no_invented_failures": False,
        "every_failure_explained": True,
    }


async def test_unexplained_failure_is_flagged(
    ctx: AgentContext, fakes: AgentFakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_client, "test_runner_client", FakeRunnerClient(fail={"TC-REG-003"}))
    rules = BusinessRules.model_validate_json(rules_json())
    cases = [TestCase.model_validate(email_case())]
    automation = await step6_test_automation.run(ctx, cases, TARGET_URL, "Register Account")
    fakes.text._responses = [narrative_json()]

    await step7_test_validation.run(ctx, rules, cases, [], automation)

    checks = {
        c["name"]: c["passed"] for c in ctx.record["steps"]["step7_test_validation"]["checks"]
    }
    assert checks["every_failure_explained"] is False
