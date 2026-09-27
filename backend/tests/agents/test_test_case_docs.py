from __future__ import annotations

from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import (
    ArtifactRef,
    BusinessRules,
    CaseRunResult,
    CaseVerdict,
    FailureAnalysis,
    StepRunResult,
    TestCase,
)
from rag_backend.agents.test_case_docs import CaseLedger
from tests.agents.fakes import email_case, first_name_case, rules_json


def _evidence(case_id: str, index: int, action: str) -> ArtifactRef:
    return ArtifactRef(
        name=f"test-cases/{case_id}/evidence/step-{index:02d}-{action}.png", bytes=1, sha256="x"
    )


def _failed_email_result() -> CaseRunResult:
    case = TestCase.model_validate(email_case())
    steps = [
        StepRunResult(
            index=index,
            action=step.action,
            locator=step.locator,
            value=step.value,
            status="failed" if index == 3 else "passed",
            error="Expected substring not found" if index == 3 else None,
            observed="text=''" if index == 3 else "ok",
            page_messages=["email-error: Email is required."] if index == 3 else [],
            evidence=_evidence(case.case_id, index + 1, step.action),
        )
        for index, step in enumerate(case.steps)
    ]
    return CaseRunResult(
        case_id=case.case_id,
        status="failed",
        duration_ms=1500,
        steps=steps,
        failure_screenshot=steps[3].evidence,
    )


def test_failed_case_doc_shows_evidence_observed_value_and_analysis(ctx: AgentContext) -> None:
    ledger = CaseLedger(ctx, BusinessRules.model_validate_json(rules_json()))
    ledger.add_design(TestCase.model_validate(email_case()), design_round=1)
    ledger.set_verdict(CaseVerdict(case_id="TC-REG-003", verdict="approved", reason="matches"))
    ledger.set_result(_failed_email_result())
    ledger.set_analysis(
        FailureAnalysis(
            case_id="TC-REG-003", suspected_cause="app_defect", explanation="no message shown"
        )
    )

    ledger.write()

    folder = ctx.root / "test-cases" / "TC-REG-003"
    doc = (folder / "test-case.md").read_text(encoding="utf-8")
    assert "❌ FAILED in 1.5s" in doc
    assert "| 4 | expect_text |" in doc
    assert "Expected substring not found" in doc
    assert "text=''" in doc
    assert "| Message shown on page |" in doc
    assert "| ❌ failed: Expected substring not found | email-error: Email is required. |" in doc
    assert "Page showed: email-error: Email is required." in doc
    assert "[screenshot](evidence/step-04-expect_text.png)" in doc
    assert "Step 4 (expect_text) failed" in doc
    assert "![Failure screenshot](evidence/step-04-expect_text.png)" in doc
    assert "**app_defect** — no message shown" in doc
    assert (folder / "result.json").is_file()
    assert ctx.record["test_cases"][0] == {
        "case_id": "TC-REG-003",
        "title": "Case TC-REG-003",
        "folder": "test-cases/TC-REG-003",
        "verdict": "approved",
        "result": "failed",
        "evidence_count": 4,
    }


def test_rejected_case_doc_says_it_was_not_executed(ctx: AgentContext) -> None:
    ledger = CaseLedger(ctx, BusinessRules.model_validate_json(rules_json()))
    ledger.add_design(TestCase.model_validate(first_name_case()), design_round=2)
    ledger.set_verdict(
        CaseVerdict(case_id="TC-REG-002", verdict="rejected", reason="wrong message text")
    )

    ledger.write()

    doc = (ctx.root / "test-cases" / "TC-REG-002" / "test-case.md").read_text(encoding="utf-8")
    assert "| Designed in round | 2 |" in doc
    assert "**rejected** — wrong message text" in doc
    assert "Not executed — rejected by the business agent." in doc
    assert not (ctx.root / "test-cases" / "TC-REG-002" / "result.json").exists()
