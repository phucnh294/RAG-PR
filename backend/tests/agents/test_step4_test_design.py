from __future__ import annotations

from rag_backend.agents import step4_test_design
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import BusinessRules, UiAnalysis
from tests.agents.conftest import AgentFakes
from tests.agents.fakes import (
    design_json,
    email_case,
    register_dom,
    rules_json,
    success_case,
    ui_analysis_json,
)


def _inputs() -> tuple[BusinessRules, UiAnalysis]:
    return (
        BusinessRules.model_validate_json(rules_json()),
        UiAnalysis.model_validate_json(ui_analysis_json()),
    )


async def test_design_logs_rules_and_ui_as_input_and_cases_as_output(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    rules, ui = _inputs()
    fakes.text._responses = [design_json()]

    design = await step4_test_design.run(ctx, 1, rules, ui, register_dom())

    step = ctx.record["steps"]["step4_test_design"]
    assert step["input"]["round"] == 1
    assert step["input"]["feedback"] is None
    assert [r["rule_id"] for r in step["input"]["rules"]["rules"]] == ["BR-001", "BR-002", "BR-003"]
    assert [c["case_id"] for c in step["output"]["cases"]] == [c.case_id for c in design.cases]
    assert all(check["passed"] for check in step["checks"]), step["checks"]


async def test_missing_goto_is_prepended_and_bad_references_are_flagged(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    rules, ui = _inputs()
    case = success_case()
    case["steps"] = case["steps"][1:]  # no goto
    case["source_rule_ids"] = ["BR-999"]
    case["steps"][0]["locator"] = {"strategy": "label", "value": "Phone"}
    fakes.text._responses = [design_json(case)]

    design = await step4_test_design.run(ctx, 1, rules, ui, register_dom())

    assert design.cases[0].steps[0].action == "goto"
    checks = {c["name"]: c["passed"] for c in ctx.record["steps"]["step4_test_design"]["checks"]}
    assert checks["cases_start_with_goto"] is False
    assert checks["source_rules_exist"] is False
    assert checks["locators_match_dom"] is False
    assert checks["all_rules_covered"] is False


async def test_revision_round_uses_its_own_step_key_and_sends_feedback(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    rules, ui = _inputs()
    fakes.text._responses = [design_json(email_case())]
    feedback = {"rejected_cases": [{"case": {"case_id": "TC-REG-003"}, "reason": "wrong text"}]}

    await step4_test_design.run(ctx, 2, rules, ui, register_dom(), feedback)

    assert "step4_test_design_r2" in ctx.record["steps"]
    assert ctx.record["steps"]["step4_test_design_r2"]["input"]["feedback"] == feedback
    assert "wrong text" in fakes.text.calls[0]["messages"][-1]["content"]
