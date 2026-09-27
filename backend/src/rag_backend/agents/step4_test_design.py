"""Step 4: the test-design agent turns the business rules into executable test cases
(structured steps, never code). On later rounds it only revises the cases the business
agent rejected, plus new cases for uncovered rules."""

from __future__ import annotations

from typing import Any

from rag_backend.agents import clients
from rag_backend.agents.checks import check, design_checks, raise_on_errors
from rag_backend.agents.llm_json import call_structured, prompt_json
from rag_backend.agents.prompts import TEST_DESIGN_REVISION_NOTE, TEST_DESIGN_SYSTEM
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import (
    BusinessRules,
    CheckResult,
    DomElement,
    TestCase,
    TestDesign,
    TestStep,
    UiAnalysis,
)


def step_name(design_round: int) -> str:
    return "step4_test_design" if design_round == 1 else f"step4_test_design_r{design_round}"


def _ensure_starts_with_goto(design: TestDesign) -> tuple[TestDesign, list[str]]:
    """Every case must start on the page under test; small models sometimes skip the
    goto. Prepending it is a mechanical fix, recorded as a check (not hidden)."""
    fixed: list[str] = []
    cases: list[TestCase] = []
    for case in design.cases:
        if not case.steps or case.steps[0].action != "goto":
            case = case.model_copy(
                update={"steps": [TestStep(action="goto", value=""), *case.steps]}
            )
            fixed.append(case.case_id)
        cases.append(case)
    return TestDesign(cases=cases), fixed


async def run(
    ctx: AgentContext,
    design_round: int,
    rules: BusinessRules,
    ui: UiAnalysis,
    dom: list[DomElement],
    feedback: dict[str, Any] | None = None,
) -> TestDesign:
    step = step_name(design_round)
    rules_json = rules.model_dump(mode="json")
    ui_json = ui.model_dump(mode="json")
    ctx.begin(
        step,
        {"round": design_round, "rules": rules_json, "ui_analysis": ui_json, "feedback": feedback},
    )
    content = (
        f"Business rules (JSON):\n{prompt_json(rules_json)}\n\n"
        f"UI analysis (JSON):\n{prompt_json(ui_json)}"
    )
    if feedback:
        content += (
            f"\n\n{TEST_DESIGN_REVISION_NOTE}\nReview feedback (JSON):\n" f"{prompt_json(feedback)}"
        )
    messages = [
        {"role": "system", "content": TEST_DESIGN_SYSTEM},
        {"role": "user", "content": content},
    ]
    raw_design = await call_structured(ctx, step, clients.agents_text_client, messages, TestDesign)
    design, fixed = _ensure_starts_with_goto(raw_design)
    checks: list[CheckResult] = design_checks(design.cases, rules, dom)
    checks.append(
        check(
            "cases_start_with_goto",
            not fixed,
            f"goto prepended to: {', '.join(fixed)}" if fixed else "every case starts with goto",
        )
    )
    ctx.finish(step, design.model_dump(mode="json"), [c.model_dump() for c in checks])
    raise_on_errors(step, checks)
    return design
