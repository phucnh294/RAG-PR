"""No-network doubles and canned agent outputs for the Agents pipeline tests.

The canned DOM mirrors what test-runner's /capture returns for myweb's Register Account
page, and the canned agent answers are shaped like real model output (JSON strings), so
the tests exercise the same parsing/validation path as production.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from rag_backend.agents.runner_client import (
    RunnerCapture,
    RunnerCase,
    RunnerCaseResult,
    RunnerRunResponse,
    RunnerStepResult,
)
from rag_backend.agents.schemas import DomElement
from rag_backend.llm_model.client import LlmClient

# 1x1 transparent PNG.
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
TARGET_URL = "http://myweb:8080/myweb/"


class ScriptedLlmClient(LlmClient):
    """Returns queued responses in order and records every call it receives."""

    def __init__(
        self, responses: list[str] | None = None, provider: str = "ollama", model: str = "fake"
    ) -> None:
        self._responses = list(responses or [])
        self._provider = provider
        self._model_name = model
        self._google_model_name = model
        self.calls: list[dict[str, Any]] = []

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | str | None = None,
        options: dict[str, Any] | None = None,
        fail_on_truncation: bool = False,
    ) -> AsyncIterator[str]:
        self.calls.append(
            {"messages": messages, "response_format": response_format, "options": options}
        )
        if not self._responses:
            raise AssertionError("ScriptedLlmClient called more times than scripted")
        yield self._responses.pop(0)


class FakeRunnerClient:
    """test-runner double: a fixed capture, and every case passes unless listed in fail."""

    def __init__(
        self, elements: list[DomElement] | None = None, fail: set[str] | None = None
    ) -> None:
        self._elements = elements if elements is not None else register_dom()
        self._fail = fail or set()
        self.captured: list[str] = []
        self.runs: list[tuple[str, list[RunnerCase]]] = []

    async def capture(self, url: str) -> RunnerCapture:
        self.captured.append(url)
        return RunnerCapture(
            final_url=url,
            title="Register Account",
            screenshot_png_b64=PNG_B64,
            aria_snapshot='- heading "Register Account" [level=1]',
            elements=self._elements,
        )

    async def run(self, base_url: str, cases: list[RunnerCase]) -> RunnerRunResponse:
        self.runs.append((base_url, cases))
        results = []
        for case in cases:
            failing = case.case_id in self._fail
            last = len(case.steps) - 1
            steps = [
                RunnerStepResult(
                    index=index,
                    action=step.action,
                    locator=step.locator,
                    value=step.value,
                    status="failed" if failing and index == last else "passed",
                    error="expect.toContainText: timeout" if failing and index == last else None,
                    observed="text=''" if failing and index == last else f"step {index} ok",
                    page_messages=(
                        ["firstName-error: First name is required."]
                        if failing and index == last
                        else []
                    ),
                    screenshot_png_b64=PNG_B64,
                )
                for index, step in enumerate(case.steps)
            ]
            results.append(
                RunnerCaseResult(
                    case_id=case.case_id,
                    status="failed" if failing else "passed",
                    duration_ms=12.5,
                    steps=steps,
                )
            )
        return RunnerRunResponse(cases=results)


def register_dom() -> list[DomElement]:
    def field(field_id: str, label: str, required: bool, **extra: Any) -> list[DomElement]:
        return [
            DomElement(
                tag="input",
                type=extra.pop("type", "text"),
                id=field_id,
                name=field_id,
                label=label,
                required=required,
                role="textbox",
                accessible_name=label,
                **extra,
            ),
            DomElement(tag="p", id=f"{field_id}-error", role="alert", visible=False),
        ]

    return [
        DomElement(
            tag="h1", role="heading", accessible_name="Register Account", text="Register Account"
        ),
        DomElement(tag="form", id="register-form", role="form", test_id="register-form"),
        *field("firstName", "First name *", True),
        *field("lastName", "Last name *", True),
        *field("dob", "Date of birth", False, placeholder="DD/MM/YYYY"),
        *field("email", "Email *", True, type="email"),
        DomElement(
            tag="button",
            type="submit",
            id="register",
            role="button",
            accessible_name="Register",
            text="Register",
        ),
        DomElement(
            tag="button",
            type="button",
            id="back",
            role="button",
            accessible_name="Back",
            text="Back",
        ),
        DomElement(
            tag="div", id="success-banner", role="status", test_id="success-banner", visible=False
        ),
    ]


def _label(value: str) -> dict[str, str]:
    return {"strategy": "label", "value": value}


REGISTER_BUTTON = {"strategy": "role", "value": "button", "name": "Register"}
BANNER = {"strategy": "testid", "value": "success-banner"}


def ui_analysis_json() -> str:
    return json.dumps(
        {
            "page_title": "Register Account",
            "purpose": "Create an account",
            "elements": [
                {
                    "element_id": "firstName",
                    "type": "textbox",
                    "label": "First name",
                    "required": True,
                    "locator": _label("First name"),
                    "source": "observed",
                },
                {
                    "element_id": "lastName",
                    "type": "textbox",
                    "label": "Last name",
                    "required": True,
                    "locator": _label("Last name"),
                    "source": "observed",
                },
                {
                    "element_id": "dob",
                    "type": "textbox",
                    "label": "Date of birth",
                    "required": False,
                    "locator": _label("Date of birth"),
                    "source": "observed",
                },
                {
                    "element_id": "email",
                    "type": "textbox",
                    "label": "Email",
                    "required": True,
                    "locator": _label("Email"),
                    "source": "observed",
                },
                {
                    "element_id": "register",
                    "type": "button",
                    "label": "Register",
                    "locator": REGISTER_BUTTON,
                    "source": "observed",
                },
                {
                    "element_id": "success-banner",
                    "type": "status",
                    "label": "Success message",
                    "locator": BANNER,
                    "source": "observed",
                },
            ],
            "messages": [],
            "navigation": ["Back clears the form"],
            "uncertainties": [],
        }
    )


def rules_json() -> str:
    return json.dumps(
        {
            "rules": [
                {
                    "rule_id": "BR-001",
                    "title": "First name required",
                    "description": "Empty first name shows an error",
                    "field": "firstName",
                    "type": "validation",
                    "source_quote": "First name is required.",
                },
                {
                    "rule_id": "BR-002",
                    "title": "Email format",
                    "description": "Email must be valid",
                    "field": "email",
                    "type": "validation",
                    "source_quote": "Email is required and must be a valid email address",
                },
                {
                    "rule_id": "BR-003",
                    "title": "Success message",
                    "description": "Valid data shows the success message",
                    "field": None,
                    "type": "behaviour",
                    "source_quote": "When all fields are valid and Register is clicked",
                },
            ]
        }
    )


def _case(case_id: str, rule: str, steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "title": extra.pop("title", f"Case {case_id}"),
        "steps": steps,
        "expected": "as the rule says",
        "source_rule_ids": [rule],
        **extra,
    }


def success_case() -> dict[str, Any]:
    return _case(
        "TC-REG-001",
        "BR-003",
        [
            {"action": "goto", "value": ""},
            {"action": "fill", "locator": _label("First name"), "value": "Long"},
            {"action": "fill", "locator": _label("Last name"), "value": "Huynh"},
            {"action": "fill", "locator": _label("Email"), "value": "abc@gmail.com"},
            {"action": "click", "locator": REGISTER_BUTTON},
            {"action": "expect_text", "locator": BANNER, "value": "Account 123"},
        ],
        title="Successful registration",
    )


def first_name_case() -> dict[str, Any]:
    return _case(
        "TC-REG-002",
        "BR-001",
        [
            {"action": "goto", "value": ""},
            {"action": "click", "locator": REGISTER_BUTTON},
            {
                "action": "expect_text",
                "locator": {"strategy": "css", "value": "#firstName-error"},
                "value": "First name is required.",
            },
        ],
    )


def email_case(expected: str = "Email must be a valid email address.") -> dict[str, Any]:
    return _case(
        "TC-REG-003",
        "BR-002",
        [
            {"action": "goto", "value": ""},
            {"action": "fill", "locator": _label("Email"), "value": "not-an-email"},
            {"action": "click", "locator": REGISTER_BUTTON},
            {
                "action": "expect_text",
                "locator": {"strategy": "css", "value": "#email-error"},
                "value": expected,
            },
        ],
    )


def design_json(*cases: dict[str, Any]) -> str:
    return json.dumps({"cases": list(cases) or [success_case(), first_name_case(), email_case()]})


def confirmation_json(rejected: dict[str, str] | None = None, *case_ids: str) -> str:
    rejected = rejected or {}
    ids = case_ids or ("TC-REG-001", "TC-REG-002", "TC-REG-003")
    return json.dumps(
        {
            "verdicts": [
                {
                    "case_id": case_id,
                    "verdict": "rejected" if case_id in rejected else "approved",
                    "reason": rejected.get(case_id, "matches the rules"),
                    "rule_ids": [],
                }
                for case_id in ids
            ],
            "uncovered_rule_ids": [],
        }
    )


def narrative_json(failures: dict[str, str] | None = None) -> str:
    return json.dumps(
        {
            "summary": "All approved cases were executed.",
            "failure_analysis": [
                {"case_id": case_id, "suspected_cause": cause, "explanation": "see step error"}
                for case_id, cause in (failures or {}).items()
            ],
        }
    )
