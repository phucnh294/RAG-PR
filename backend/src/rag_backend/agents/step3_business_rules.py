"""Step 3: the business-analysis agent extracts testable business rules from the
requirement text, mapped onto the UI elements from step 2."""

from __future__ import annotations

from rag_backend.agents import clients
from rag_backend.agents.checks import business_rules_checks, raise_on_errors
from rag_backend.agents.llm_json import call_structured, prompt_json
from rag_backend.agents.prompts import BUSINESS_RULES_SYSTEM
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import BusinessRules, UiAnalysis

STEP = "step3_business_rules"


async def run(ctx: AgentContext, requirement: str, ui: UiAnalysis) -> BusinessRules:
    ui_json = ui.model_dump(mode="json")
    ctx.begin(STEP, {"requirement": requirement, "ui_analysis": ui_json})
    messages = [
        {"role": "system", "content": BUSINESS_RULES_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Requirement text:\n{requirement}\n\n"
                f"UI analysis (JSON):\n{prompt_json(ui_json)}"
            ),
        },
    ]
    rules = await call_structured(ctx, STEP, clients.agents_text_client, messages, BusinessRules)
    checks = business_rules_checks(rules, requirement, ui)
    ctx.finish(STEP, rules.model_dump(mode="json"), [c.model_dump() for c in checks])
    raise_on_errors(STEP, checks)
    return rules
