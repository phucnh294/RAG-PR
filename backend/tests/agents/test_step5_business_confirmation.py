from __future__ import annotations

import json

from rag_backend.agents import step5_business_confirmation
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import BusinessRules, TestDesign
from tests.agents.conftest import AgentFakes
from tests.agents.fakes import confirmation_json, design_json, rules_json


def _inputs() -> tuple[BusinessRules, TestDesign]:
    return (
        BusinessRules.model_validate_json(rules_json()),
        TestDesign.model_validate_json(design_json()),
    )


async def test_confirmation_logs_cases_as_input_and_verdicts_as_output(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    rules, design = _inputs()
    fakes.text._responses = [confirmation_json({"TC-REG-003": "Expected text is wrong"})]

    confirmation = await step5_business_confirmation.run(ctx, 1, rules, design.cases)

    step = ctx.record["steps"]["step5_business_confirmation"]
    assert [c["case_id"] for c in step["input"]["cases"]] == [
        "TC-REG-001",
        "TC-REG-002",
        "TC-REG-003",
    ]
    verdicts = {v.case_id: v.verdict for v in confirmation.verdicts}
    assert verdicts == {
        "TC-REG-001": "approved",
        "TC-REG-002": "approved",
        "TC-REG-003": "rejected",
    }
    # BR-002 was only covered by the rejected case -> recomputed as uncovered.
    assert confirmation.uncovered_rule_ids == ["BR-002"]
    assert step["output"]["uncovered_rule_ids"] == ["BR-002"]


async def test_missing_verdict_becomes_rejection_and_unknown_ids_are_dropped(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    rules, design = _inputs()
    answer = {
        "verdicts": [
            {"case_id": "TC-REG-001", "verdict": "approved", "reason": "ok"},
            {"case_id": "TC-REG-002", "verdict": "approved", "reason": "ok"},
            {"case_id": "TC-REG-999", "verdict": "approved", "reason": "ok"},
        ]
    }
    fakes.text._responses = [json.dumps(answer)]

    confirmation = await step5_business_confirmation.run(ctx, 1, rules, design.cases)

    verdict = next(v for v in confirmation.verdicts if v.case_id == "TC-REG-003")
    assert verdict.verdict == "rejected"
    assert {v.case_id for v in confirmation.verdicts} == {"TC-REG-001", "TC-REG-002", "TC-REG-003"}
    checks = {
        c["name"]: c["passed"] for c in ctx.record["steps"]["step5_business_confirmation"]["checks"]
    }
    assert checks["verdict_for_every_case"] is False
    assert checks["no_unknown_case_ids"] is False
