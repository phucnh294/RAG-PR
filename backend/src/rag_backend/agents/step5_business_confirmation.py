"""Step 5: the business-analysis agent reviews every designed case against the rules and
approves or rejects it. Coverage is recomputed by code from the approved cases."""

from __future__ import annotations

from rag_backend.agents import clients
from rag_backend.agents.checks import check
from rag_backend.agents.llm_json import call_structured, prompt_json
from rag_backend.agents.prompts import BUSINESS_CONFIRMATION_SYSTEM
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import (
    BusinessConfirmation,
    BusinessRules,
    CaseVerdict,
    TestCase,
)

_NO_VERDICT_REASON = "No verdict returned by the business agent; treated as rejected."


def step_name(design_round: int) -> str:
    return (
        "step5_business_confirmation"
        if design_round == 1
        else f"step5_business_confirmation_r{design_round}"
    )


def _normalize(
    confirmation: BusinessConfirmation, cases: list[TestCase], rules: BusinessRules
) -> tuple[BusinessConfirmation, list[str], list[str]]:
    """Exactly one verdict per reviewed case (missing -> rejected, unknown ids dropped),
    and uncovered_rule_ids recomputed from the approved cases."""
    case_ids = [case.case_id for case in cases]
    by_id: dict[str, CaseVerdict] = {}
    unknown: list[str] = []
    for verdict in confirmation.verdicts:
        if verdict.case_id in case_ids:
            by_id.setdefault(verdict.case_id, verdict)
        else:
            unknown.append(verdict.case_id)
    missing = [case_id for case_id in case_ids if case_id not in by_id]
    verdicts = [
        by_id.get(case_id)
        or CaseVerdict(case_id=case_id, verdict="rejected", reason=_NO_VERDICT_REASON)
        for case_id in case_ids
    ]
    approved = {v.case_id for v in verdicts if v.verdict == "approved"}
    covered = {r for case in cases if case.case_id in approved for r in case.source_rule_ids}
    uncovered = sorted({rule.rule_id for rule in rules.rules} - covered)
    return BusinessConfirmation(verdicts=verdicts, uncovered_rule_ids=uncovered), missing, unknown


async def run(
    ctx: AgentContext, design_round: int, rules: BusinessRules, cases: list[TestCase]
) -> BusinessConfirmation:
    step = step_name(design_round)
    rules_json = rules.model_dump(mode="json")
    cases_json = [case.model_dump(mode="json") for case in cases]
    ctx.begin(step, {"round": design_round, "rules": rules_json, "cases": cases_json})
    messages = [
        {"role": "system", "content": BUSINESS_CONFIRMATION_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Business rules (JSON):\n{prompt_json(rules_json)}\n\n"
                f"Test cases to review (JSON):\n{prompt_json(cases_json)}"
            ),
        },
    ]
    raw = await call_structured(
        ctx, step, clients.agents_text_client, messages, BusinessConfirmation
    )
    confirmation, missing, unknown = _normalize(raw, cases, rules)
    llm_uncovered = sorted(set(raw.uncovered_rule_ids))
    approved = sum(v.verdict == "approved" for v in confirmation.verdicts)
    checks = [
        check(
            "verdict_for_every_case",
            not missing,
            f"no verdict for: {', '.join(missing)}" if missing else f"{len(cases)} verdict(s)",
        ),
        check(
            "no_unknown_case_ids",
            not unknown,
            f"verdicts for unknown cases: {', '.join(unknown)}" if unknown else "",
        ),
        check(
            "uncovered_rules_match_computed",
            llm_uncovered == confirmation.uncovered_rule_ids,
            f"agent said {llm_uncovered}, computed {confirmation.uncovered_rule_ids}",
        ),
        check("approved_count", approved > 0, f"{approved}/{len(cases)} approved"),
    ]
    ctx.finish(step, confirmation.model_dump(mode="json"), [c.model_dump() for c in checks])
    return confirmation
