"""Step 6: test automation — render the approved cases as a Playwright .spec.ts and
execute the same steps in the test-runner container."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from rag_backend.agents import artifacts, runner_client
from rag_backend.agents.checks import check, raise_on_errors
from rag_backend.agents.run_layout import AUTOMATION_FOLDER, case_folder, safe_segment
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.runner_client import RunnerCase, RunnerCaseResult
from rag_backend.agents.schemas import (
    ArtifactRef,
    AutomationInput,
    AutomationResult,
    CaseRunResult,
    CheckResult,
    StepRunResult,
    TestCase,
    TestStep,
)
from rag_backend.agents.spec_render import render_spec_ts

STEP = "step6_test_automation"


def _pin_gotos_to_target(case: TestCase, base_url: str) -> tuple[TestCase, bool]:
    """A goto the agent pointed at another host (e.g. a localhost URL copied from the
    requirement) is rewritten to the page under test: the browser must never leave the
    allowed target (see agents_allowed_target_hosts)."""
    target_host = urlparse(base_url).hostname
    changed = False
    steps: list[TestStep] = []
    for step in case.steps:
        resolved_host = urlparse(urljoin(base_url, step.value or "")).hostname
        if step.action == "goto" and resolved_host != target_host:
            step = TestStep(action="goto", value="")
            changed = True
        steps.append(step)
    return case.model_copy(update={"steps": steps}), changed


def _save_evidence(ctx: AgentContext, raw: RunnerCaseResult) -> CaseRunResult:
    """Move the runner's base64 screenshots into test-cases/{id}/evidence/ files and keep
    only references in the log. The failing step's screenshot doubles as the failure
    screenshot."""
    folder = case_folder(raw.case_id)
    steps: list[StepRunResult] = []
    failure_screenshot: ArtifactRef | None = None
    for step in raw.steps:
        evidence = None
        if step.screenshot_png_b64:
            rel = f"{folder}/evidence/step-{step.index + 1:02d}-{step.action}.png"
            evidence = artifacts.save_png_b64(ctx.root, rel, step.screenshot_png_b64)
        if step.status == "failed" and evidence is not None:
            failure_screenshot = evidence
        steps.append(
            StepRunResult.model_validate(
                step.model_dump(exclude={"screenshot_png_b64", "evidence"}) | {"evidence": evidence}
            )
        )
    if failure_screenshot is None and raw.failure_screenshot_png_b64:
        failure_screenshot = artifacts.save_png_b64(
            ctx.root, f"{folder}/evidence/failure.png", raw.failure_screenshot_png_b64
        )
    return CaseRunResult(
        case_id=raw.case_id,
        status=raw.status,  # type: ignore[arg-type]
        duration_ms=raw.duration_ms,
        steps=steps,
        failure_screenshot=failure_screenshot,
        console_errors=raw.console_errors,
    )


async def run(
    ctx: AgentContext, cases: list[TestCase], base_url: str, suite_title: str
) -> AutomationResult:
    ctx.begin(
        STEP, AutomationInput(base_url=base_url, approved_cases=cases).model_dump(mode="json")
    )
    to_run: list[TestCase] = []
    repinned: list[str] = []
    for case in cases:
        if not case.automation_candidate:
            continue
        pinned, changed = _pin_gotos_to_target(case, base_url)
        to_run.append(pinned)
        if changed:
            repinned.append(case.case_id)
    not_automated = [case.case_id for case in cases if not case.automation_candidate]

    spec_ref = None
    results: list[CaseRunResult] = []
    if to_run:
        spec = render_spec_ts(to_run, base_url, suite_title, ctx.run_id)
        spec_rel = f"{AUTOMATION_FOLDER}/{safe_segment(suite_title)}.spec.ts"
        spec_ref = artifacts.save_text(ctx.root, spec_rel, spec)
        response = await runner_client.test_runner_client.run(
            base_url,
            [RunnerCase(case_id=c.case_id, title=c.title, steps=c.steps) for c in to_run],
        )
        results = [_save_evidence(ctx, raw) for raw in response.cases]

    executed = [case.case_id for case in to_run]
    returned = {result.case_id for result in results}
    missing = [case_id for case_id in executed if case_id not in returned]
    automation = AutomationResult(
        base_url=base_url,
        executed_case_ids=executed,
        not_automated_case_ids=not_automated,
        results=results,
        spec_ts=spec_ref,
    )
    checks: list[CheckResult] = [
        check("has_cases_to_run", bool(to_run), f"{len(to_run)} case(s) executed"),
        check(
            "result_for_every_case",
            not missing,
            f"no result for: {', '.join(missing)}" if missing else "every case has a result",
            "error",
        ),
        check(
            "gotos_on_target",
            not repinned,
            (
                f"goto rewritten to the target page in: {', '.join(repinned)}"
                if repinned
                else "every goto stays on the target page"
            ),
        ),
    ]
    ctx.finish(STEP, automation.model_dump(mode="json"), [c.model_dump() for c in checks])
    raise_on_errors(STEP, checks)
    return automation
