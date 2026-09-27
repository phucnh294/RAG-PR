"""Runs real Chromium against the real myweb container, so these tests double as the
Register Account page's regression suite.

    docker compose run --rm test-runner python -m pytest
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import CaptureRequest, CaseResult, Locator, RunRequest, TestCaseSpec, TestStep  # noqa: E402
from runner import capture_page, run_cases  # noqa: E402

MYWEB_URL = os.environ.get("MYWEB_URL", "http://myweb:8080/myweb/")


def _label(text: str) -> Locator:
    return Locator(strategy="label", value=text)


def _fill(label: str, value: str) -> TestStep:
    return TestStep(action="fill", locator=_label(label), value=value)


def _register() -> TestStep:
    return TestStep(
        action="click", locator=Locator(strategy="role", value="button", name="Register")
    )


def _banner_has(text: str) -> TestStep:
    return TestStep(
        action="expect_text", locator=Locator(strategy="testid", value="success-banner"), value=text
    )


def _error_has(field_id: str, text: str) -> TestStep:
    return TestStep(
        action="expect_text", locator=Locator(strategy="css", value=f"#{field_id}-error"), value=text
    )


async def _run(*cases: TestCaseSpec) -> dict[str, CaseResult]:
    results = await run_cases(RunRequest(base_url=MYWEB_URL, cases=list(cases)))
    return {result.case_id: result for result in results}


async def test_capture_reports_form_fields_with_labels_and_required_flags() -> None:
    capture = await capture_page(CaptureRequest(url=MYWEB_URL))

    assert capture.title == "Register Account"
    assert capture.screenshot_png_b64
    assert len(capture.vision_png_b64) < len(capture.screenshot_png_b64)
    inputs = {element.id: element for element in capture.elements if element.tag == "input"}
    assert set(inputs) == {"firstName", "lastName", "dob", "email"}
    assert inputs["firstName"].label == "First name *"
    assert inputs["firstName"].required is True
    assert inputs["dob"].required is False
    banner = next(e for e in capture.elements if e.test_id == "success-banner")
    assert banner.visible is False
    assert "Register Account" in capture.aria_snapshot


async def test_valid_registration_shows_account_123_banner() -> None:
    case = TestCaseSpec(
        case_id="TC-OK",
        steps=[
            TestStep(action="goto", value=""),
            _fill("First name", "Long"),
            _fill("Last name", "Huynh"),
            _fill("Date of birth", "01/01/2000"),
            _fill("Email", "abc@gmail.com"),
            _register(),
            _banner_has("Account 123 has been created successfully!"),
            TestStep(action="expect_value", locator=_label("First name"), value=""),
        ],
    )

    result = (await _run(case))["TC-OK"]

    assert result.status == "passed", result.steps


async def test_missing_required_fields_show_errors_and_no_banner() -> None:
    case = TestCaseSpec(
        case_id="TC-REQ",
        steps=[
            TestStep(action="goto", value=""),
            _register(),
            _error_has("firstName", "First name is required."),
            _error_has("lastName", "Last name is required."),
            _error_has("email", "Email is required."),
            TestStep(action="expect_hidden", locator=Locator(strategy="css", value="#dob-error")),
            TestStep(
                action="expect_hidden", locator=Locator(strategy="testid", value="success-banner")
            ),
        ],
    )

    result = (await _run(case))["TC-REQ"]

    assert result.status == "passed", result.steps


async def test_invalid_email_and_dob_formats_are_rejected() -> None:
    case = TestCaseSpec(
        case_id="TC-FMT",
        steps=[
            TestStep(action="goto", value=""),
            _fill("First name", "Long"),
            _fill("Last name", "Huynh"),
            _fill("Date of birth", "2000-01-01"),
            _fill("Email", "not-an-email"),
            _register(),
            _error_has("email", "Email must be a valid email address."),
            _error_has("dob", "Date of birth must be in DD/MM/YYYY format."),
        ],
    )

    result = (await _run(case))["TC-FMT"]

    assert result.status == "passed", result.steps


async def test_future_dob_and_long_name_are_rejected() -> None:
    case = TestCaseSpec(
        case_id="TC-BOUND",
        steps=[
            TestStep(action="goto", value=""),
            _fill("First name", "A" * 51),
            _fill("Last name", "Huynh"),
            _fill("Date of birth", "01/01/2999"),
            _fill("Email", "abc@gmail.com"),
            _register(),
            _error_has("firstName", "First name must be at most 50 characters."),
            _error_has("dob", "Date of birth cannot be in the future."),
        ],
    )

    result = (await _run(case))["TC-BOUND"]

    assert result.status == "passed", result.steps


async def test_back_resets_form_and_clears_errors() -> None:
    case = TestCaseSpec(
        case_id="TC-BACK",
        steps=[
            TestStep(action="goto", value=""),
            _fill("First name", "Long"),
            _register(),
            TestStep(action="click", locator=Locator(strategy="role", value="button", name="Back")),
            TestStep(action="expect_value", locator=_label("First name"), value=""),
            TestStep(
                action="expect_hidden", locator=Locator(strategy="css", value="#lastName-error")
            ),
        ],
    )

    result = (await _run(case))["TC-BACK"]

    assert result.status == "passed", result.steps


async def test_failing_step_stops_case_skips_rest_and_captures_screenshot() -> None:
    case = TestCaseSpec(
        case_id="TC-FAIL",
        steps=[
            TestStep(action="goto", value=""),
            TestStep(
                action="expect_visible", locator=Locator(strategy="testid", value="success-banner")
            ),
            _register(),
        ],
    )
    request = RunRequest(base_url=MYWEB_URL, cases=[case], default_timeout_ms=500)

    result = (await run_cases(request))[0]

    assert result.status == "failed"
    assert [step.status for step in result.steps] == ["passed", "failed", "skipped"]
    assert result.steps[1].error
    # Evidence for every executed step, including the failing one; none for skipped.
    assert result.steps[0].screenshot_png_b64 and result.steps[1].screenshot_png_b64
    assert result.steps[2].screenshot_png_b64 is None
    assert result.steps[1].observed == "visible=False"


async def test_evidence_records_what_the_page_actually_showed() -> None:
    case = TestCaseSpec(
        case_id="TC-EVIDENCE",
        steps=[
            TestStep(action="goto", value=""),
            _fill("Email", "not-an-email"),
            _register(),
            _error_has("email", "Email must be a valid email address."),
            # Deliberately wrong expectation: the observed text proves why it failed.
            _error_has("firstName", "Something else"),
        ],
    )
    request = RunRequest(base_url=MYWEB_URL, cases=[case], default_timeout_ms=500)

    result = (await run_cases(request))[0]

    observed = [step.observed for step in result.steps]
    assert observed[0].startswith("url=http://myweb:8080/myweb/")
    assert observed[1] == "value='not-an-email'"
    assert observed[3] == "text='Email must be a valid email address.'"
    assert result.steps[4].status == "failed"
    assert observed[4] == "text='First name is required.'"
    assert all(step.screenshot_png_b64 for step in result.steps)


async def test_page_messages_show_the_error_or_success_the_user_saw() -> None:
    empty = TestCaseSpec(
        case_id="TC-MSG-ERR", steps=[TestStep(action="goto", value=""), _register()]
    )
    valid = TestCaseSpec(
        case_id="TC-MSG-OK",
        steps=[
            TestStep(action="goto", value=""),
            _fill("First name", "Long"),
            _fill("Last name", "Huynh"),
            _fill("Email", "abc@gmail.com"),
            _register(),
        ],
    )
    request = RunRequest(base_url=MYWEB_URL, cases=[empty, valid])

    error_case, ok_case = await run_cases(request)

    assert error_case.steps[0].page_messages == []
    assert "firstName-error: First name is required." in error_case.steps[1].page_messages
    assert "email-error: Email is required." in error_case.steps[1].page_messages
    assert ok_case.steps[-1].page_messages == [
        "success-banner: Account 123 has been created successfully!"
    ]


async def test_evidence_can_be_turned_off() -> None:
    case = TestCaseSpec(case_id="TC-NOEVIDENCE", steps=[TestStep(action="goto", value="")])
    request = RunRequest(base_url=MYWEB_URL, cases=[case], capture_evidence=False)

    result = (await run_cases(request))[0]

    assert result.steps[0].screenshot_png_b64 is None
    assert result.steps[0].observed is None


async def test_each_case_gets_a_fresh_context_so_account_number_restarts() -> None:
    def registration(case_id: str) -> TestCaseSpec:
        return TestCaseSpec(
            case_id=case_id,
            steps=[
                TestStep(action="goto", value=""),
                _fill("First name", "Long"),
                _fill("Last name", "Huynh"),
                _fill("Email", "abc@gmail.com"),
                _register(),
                _banner_has("Account 123"),
            ],
        )

    results = await _run(registration("A"), registration("B"))

    assert results["A"].status == "passed"
    assert results["B"].status == "passed"
