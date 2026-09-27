from __future__ import annotations

import json

from rag_backend.agents import step3_business_rules
from rag_backend.agents.defaults import DEFAULT_REGISTER_REQUIREMENT
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import UiAnalysis
from tests.agents.conftest import AgentFakes
from tests.agents.fakes import rules_json, ui_analysis_json


async def test_business_agent_gets_requirement_and_ui_and_quotes_are_checked(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    ui = UiAnalysis.model_validate_json(ui_analysis_json())
    fakes.text._responses = [rules_json()]

    rules = await step3_business_rules.run(ctx, DEFAULT_REGISTER_REQUIREMENT, ui)

    content = fakes.text.calls[0]["messages"][-1]["content"]
    assert DEFAULT_REGISTER_REQUIREMENT in content
    step = ctx.record["steps"]["step3_business_rules"]
    assert step["input"]["requirement"] == DEFAULT_REGISTER_REQUIREMENT
    assert step["input"]["ui_analysis"]["page_title"] == "Register Account"
    assert [r["rule_id"] for r in step["output"]["rules"]] == [r.rule_id for r in rules.rules]
    assert all(check["passed"] for check in step["checks"])


async def test_invented_quote_and_unknown_field_are_flagged(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    ui = UiAnalysis.model_validate_json(ui_analysis_json())
    answer = json.loads(rules_json())
    answer["rules"][0]["source_quote"] = "Passwords must have 12 characters."
    answer["rules"][1]["field"] = "phone"
    fakes.text._responses = [json.dumps(answer)]

    await step3_business_rules.run(ctx, DEFAULT_REGISTER_REQUIREMENT, ui)

    checks = {c["name"]: c for c in ctx.record["steps"]["step3_business_rules"]["checks"]}
    assert checks["source_quotes_in_requirement"]["passed"] is False
    assert "BR-001" in checks["source_quotes_in_requirement"]["detail"]
    assert checks["fields_exist_in_ui"]["passed"] is False
