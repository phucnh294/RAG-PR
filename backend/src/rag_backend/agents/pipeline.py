"""Agents pipeline orchestrator.

    step1_capture                 test-runner loads the page: screenshot + DOM elements
    step2_ui_analysis             vision agent: UI contract (elements, locators, messages)
    step3_business_rules          business agent: rules from the requirement text
    step4_test_design[_rN]        test-design agent: executable test cases
    step5_business_confirmation   business agent: approve/reject each case (rejected cases
      [_rN]                       go back to step 4 with the reasons, up to N rounds)
    step6_test_automation         .spec.ts + execution of approved cases in Playwright
    step7_test_validation         metrics by code + validation agent's failure analysis

Every step logs its exact input and output (plus each LLM attempt and its contract checks)
into one run record, rewritten after every change so the Agents tab can follow along.

Agents hand over through files: each step writes its output to a Markdown handoff file
(handoff.py, agents_result_dir/{agent}/output/), and the next step's input is parsed back
from those files — never passed along in memory. What is on disk is what ran.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from rag_backend.agents import (
    clients,
    handoff,
    run_store,
    step1_capture,
    step2_ui_analysis,
    step3_business_rules,
    step4_test_design,
    step5_business_confirmation,
    step6_test_automation,
    step7_test_validation,
)
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import (
    AutomationInput,
    AutomationResult,
    BusinessConfirmation,
    BusinessRules,
    CaptureResult,
    DomElement,
    DroppedCase,
    TestCase,
    TestDesign,
    UiAnalysis,
    ValidationReport,
)
from rag_backend.agents.test_case_docs import CaseLedger
from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.exceptions import AgentRunInProgressError, AgentTargetNotAllowedError
from rag_backend.pipeline_logging import StepRecorder, new_request_id

logger = logging.getLogger(__name__)

# One run at a time: the vision model and the browser share one CPU box, and concurrent
# runs would only make every run slower. The active id (run_store) is set synchronously in
# start_run (no await between the check and the set), so two simultaneous requests cannot
# both pass.


def active_run_id() -> str | None:
    return run_store.active_run_id()


def models_info() -> dict[str, dict[str, str]]:
    return {
        "vision": {
            "provider": clients.vision_client.provider,
            "model": clients.vision_client.model_name,
        },
        "text": {
            "provider": clients.agents_text_client.provider,
            "model": clients.agents_text_client.model_name,
        },
    }


def validate_target_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise AgentTargetNotAllowedError(f"Target must be an http(s) URL, got {url!r}")
    if parsed.hostname not in settings.agents_allowed_target_hosts:
        raise AgentTargetNotAllowedError(
            f"Host {parsed.hostname!r} is not an allowed target "
            f"(allowed: {', '.join(settings.agents_allowed_target_hosts)})"
        )
    return url.strip()


def start_run(user: CurrentUser, target_url: str, requirement: str) -> dict[str, Any]:
    """Validate, create and persist a queued run; the caller schedules
    run_agents_pipeline(record) in the background."""
    active = run_store.active_run_id()
    if active is not None:
        raise AgentRunInProgressError(f"Agents run {active} is still in progress")
    target = validate_target_url(target_url)
    run_id = new_request_id()
    record = run_store.new_run_record(run_id, user, target, requirement, models_info())
    run_store.set_active_run(run_id)
    run_store.persist(record)
    logger.info("Agents run %s queued by %s for %s", run_id, user.username, target)
    return record


async def _design_and_confirm(
    ctx: AgentContext,
    rules: BusinessRules,
    ui: UiAnalysis,
    dom: list[DomElement],
    ledger: CaseLedger,
) -> tuple[list[TestCase], list[DroppedCase]]:
    approved: dict[str, TestCase] = {}
    latest: dict[str, TestCase] = {}
    reasons: dict[str, str] = {}
    feedback: dict[str, Any] | None = None
    rounds: list[dict[str, Any]] = []
    ctx.record["design_rounds"] = rounds

    for design_round in range(1, max(1, settings.agents_max_design_rounds) + 1):
        design_step = step4_test_design.step_name(design_round)
        await step4_test_design.run(ctx, design_round, rules, ui, dom, feedback)
        design = handoff.read_output(ctx.record, design_step, TestDesign)
        batch = [case for case in design.cases if case.case_id not in approved]
        for case in batch:
            latest[case.case_id] = case
            ledger.add_design(case, design_round)
        ledger.write()
        confirm_step = step5_business_confirmation.step_name(design_round)
        await step5_business_confirmation.run(ctx, design_round, rules, batch)
        confirmation = handoff.read_output(ctx.record, confirm_step, BusinessConfirmation)
        for verdict in confirmation.verdicts:
            ledger.set_verdict(verdict)
        ledger.write()

        rejected = []
        for verdict in confirmation.verdicts:
            if verdict.verdict == "approved":
                approved[verdict.case_id] = latest[verdict.case_id]
                reasons.pop(verdict.case_id, None)
            else:
                rejected.append(verdict)
                reasons[verdict.case_id] = verdict.reason
        covered = {r for case in approved.values() for r in case.source_rule_ids}
        uncovered = sorted({rule.rule_id for rule in rules.rules} - covered)
        rounds.append(
            {
                "round": design_round,
                "designed": [case.case_id for case in batch],
                "approved": [v.case_id for v in confirmation.verdicts if v.verdict == "approved"],
                "rejected": [v.case_id for v in rejected],
                "uncovered_rule_ids": uncovered,
            }
        )
        ctx.persist()
        if not rejected and not uncovered:
            break
        feedback = {
            "rejected_cases": [
                {"case": latest[v.case_id].model_dump(mode="json"), "reason": v.reason}
                for v in rejected
            ],
            "uncovered_rule_ids": uncovered,
            "approved_case_ids": sorted(approved),
        }

    dropped = [
        DroppedCase(case_id=case_id, title=case.title, reason=reasons.get(case_id, "rejected"))
        for case_id, case in latest.items()
        if case_id not in approved
    ]
    return list(approved.values()), dropped


async def run_agents_pipeline(record: dict[str, Any]) -> None:
    """Run every step for a record created by start_run. Never raises: a failure is
    recorded on the failing step and on the run, so the log explains it."""
    ctx = AgentContext(
        run_id=record["run_id"],
        record=record,
        recorder=StepRecorder(logger, "agents", record),
    )
    record["status"] = "running"
    record["started_at"] = run_store.now_iso()
    ctx.persist()
    try:
        await step1_capture.run(ctx, record["target_url"])
        capture = handoff.read_output(record, step1_capture.STEP, CaptureResult)
        await step2_ui_analysis.run(ctx, capture)
        ui = handoff.read_output(record, step2_ui_analysis.STEP, UiAnalysis)
        await step3_business_rules.run(ctx, record["requirement"], ui)
        rules = handoff.read_output(record, step3_business_rules.STEP, BusinessRules)
        ledger = CaseLedger(ctx, rules)
        approved, dropped = await _design_and_confirm(ctx, rules, ui, capture.elements, ledger)
        await step6_test_automation.run(
            ctx, approved, capture.final_url, ui.page_title or capture.title
        )
        automation = handoff.read_output(record, step6_test_automation.STEP, AutomationResult)
        executed = handoff.read_input(record, step6_test_automation.STEP, AutomationInput)
        for result in automation.results:
            ledger.set_result(result)
        ledger.write()
        rules = handoff.read_output(record, step3_business_rules.STEP, BusinessRules)
        await step7_test_validation.run(ctx, rules, executed.approved_cases, dropped, automation)
        report = handoff.read_output(record, step7_test_validation.STEP, ValidationReport)
        for analysis in report.failure_analysis:
            ledger.set_analysis(analysis)
        ledger.write()
        record["report"] = report.model_dump(mode="json")
        record["status"] = "succeeded"
    except Exception as error:  # background task: record the failure, never crash
        message = f"{type(error).__name__}: {error}"
        logger.exception("Agents run %s failed at %s", ctx.run_id, record.get("current_step"))
        step = record.get("current_step")
        if step:
            ctx.fail(step, message)
        record["status"] = "failed"
        record["error"] = message
    finally:
        record["finished_at"] = run_store.now_iso()
        record["current_step"] = None
        ctx.persist()
        run_store.set_active_run(None)
        logger.info("Agents run %s finished: %s", ctx.run_id, record["status"])
