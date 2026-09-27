from __future__ import annotations

import json

import pytest

from rag_backend.agents import runner_client, step6_test_automation
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import TestCase
from tests.agents.conftest import AgentFakes
from tests.agents.fakes import (
    PNG_B64,
    TARGET_URL,
    FakeRunnerClient,
    email_case,
    first_name_case,
    success_case,
)


def _cases(*raw: dict) -> list[TestCase]:  # type: ignore[type-arg]
    return [TestCase.model_validate(case) for case in raw]


async def test_automation_runs_cases_writes_spec_and_logs_results(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    cases = _cases(success_case(), first_name_case())

    automation = await step6_test_automation.run(ctx, cases, TARGET_URL, "Register Account")

    base_url, sent = fakes.runner.runs[0]
    assert base_url == TARGET_URL
    assert [case.case_id for case in sent] == ["TC-REG-001", "TC-REG-002"]
    assert automation.spec_ts is not None
    assert automation.spec_ts.name == "automation/Register_Account.spec.ts"
    spec = (ctx.root / automation.spec_ts.name).read_text(encoding="utf-8")
    assert "TC-REG-001 — Successful registration" in spec
    step = ctx.record["steps"]["step6_test_automation"]
    assert [c["case_id"] for c in step["input"]["approved_cases"]] == ["TC-REG-001", "TC-REG-002"]
    assert [r["status"] for r in step["output"]["results"]] == ["passed", "passed"]


async def test_failure_screenshot_is_saved_as_artifact_not_inlined(
    ctx: AgentContext, fakes: AgentFakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_client, "test_runner_client", FakeRunnerClient(fail={"TC-REG-003"}))

    automation = await step6_test_automation.run(
        ctx, _cases(email_case()), TARGET_URL, "Register Account"
    )

    result = automation.results[0]
    assert result.status == "failed"
    # Every executed step has its own evidence screenshot + observed value, in the
    # case's evidence folder; the failing step's screenshot is the failure screenshot.
    names = [step.evidence.name for step in result.steps if step.evidence]
    assert names == [
        "test-cases/TC-REG-003/evidence/step-01-goto.png",
        "test-cases/TC-REG-003/evidence/step-02-fill.png",
        "test-cases/TC-REG-003/evidence/step-03-click.png",
        "test-cases/TC-REG-003/evidence/step-04-expect_text.png",
    ]
    assert all((ctx.root / name).is_file() for name in names)
    assert result.failure_screenshot == result.steps[-1].evidence
    assert result.steps[-1].observed == "text=''"
    assert PNG_B64 not in json.dumps(ctx.record)


async def test_goto_to_another_host_is_pinned_to_the_target(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    case = success_case()
    case["steps"][0] = {"action": "goto", "value": "http://169.254.169.254/latest/meta-data"}

    await step6_test_automation.run(ctx, _cases(case), TARGET_URL, "Register Account")

    sent_goto = fakes.runner.runs[0][1][0].steps[0]
    assert sent_goto.value == ""
    checks = {
        c["name"]: c["passed"] for c in ctx.record["steps"]["step6_test_automation"]["checks"]
    }
    assert checks["gotos_on_target"] is False


async def test_non_automation_candidates_are_not_executed(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    manual = first_name_case() | {"automation_candidate": False}

    automation = await step6_test_automation.run(
        ctx, _cases(success_case(), manual), TARGET_URL, "Register Account"
    )

    assert automation.executed_case_ids == ["TC-REG-001"]
    assert automation.not_automated_case_ids == ["TC-REG-002"]
