"""Request/response contracts of the test-runner service.

The backend keeps a copy of the step DSL in rag_backend/agents/schemas.py; the two must
stay in sync (the backend's tests pin the JSON shape it sends).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LocatorStrategy = Literal["role", "label", "testid", "text", "css"]
StepAction = Literal[
    "goto",
    "fill",
    "click",
    "expect_visible",
    "expect_hidden",
    "expect_text",
    "expect_value",
    "expect_url",
]


class Locator(BaseModel):
    strategy: LocatorStrategy
    value: str
    # Accessible name, only used by the "role" strategy (get_by_role(value, name=name)).
    name: str | None = None
    exact: bool = False


class TestStep(BaseModel):
    __test__ = False  # not a pytest test class, despite the name

    action: StepAction
    locator: Locator | None = None
    value: str | None = None


class TestCaseSpec(BaseModel):
    __test__ = False  # not a pytest test class, despite the name

    case_id: str
    title: str = ""
    steps: list[TestStep]


class RunRequest(BaseModel):
    base_url: str
    cases: list[TestCaseSpec]
    default_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    # Screenshot + observed value after every executed step (the proof a case passed or
    # failed). Off -> only a screenshot of the failing step.
    capture_evidence: bool = True


class StepResult(BaseModel):
    index: int
    action: StepAction
    locator: Locator | None = None
    value: str | None = None
    status: Literal["passed", "failed", "skipped"]
    error: str | None = None
    duration_ms: float = 0.0
    # What the browser actually showed for this step: the element's text (expect_text),
    # the field's value (fill/expect_value), visibility (expect_visible/hidden), the URL
    # (goto/expect_url), and how many elements the locator matched.
    observed: str | None = None
    # Every message visible on the page right after the step ([role=alert], [role=status],
    # [aria-live]), e.g. "firstName-error: First name is required." — shows what the user
    # saw, success or failure, whatever element the step itself targeted.
    page_messages: list[str] = []
    # Full-page screenshot taken right after the step ran (passed or failed).
    screenshot_png_b64: str | None = None


class CaseResult(BaseModel):
    case_id: str
    status: Literal["passed", "failed", "error"]
    duration_ms: float
    steps: list[StepResult]
    failure_screenshot_png_b64: str | None = None
    console_errors: list[str] = []


class RunResponse(BaseModel):
    cases: list[CaseResult]


class CaptureRequest(BaseModel):
    url: str
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=800, ge=240, le=2160)
    # Width of the extra, downscaled screenshot for the vision model. Image tokens grow
    # with pixel area: 1280 px wide was ~2000 tokens for qwen2.5vl, 640 px is ~1/4 of that.
    vision_max_width: int = Field(default=640, ge=224, le=3840)


class DomElement(BaseModel):
    tag: str
    type: str | None = None
    id: str | None = None
    name: str | None = None
    label: str | None = None
    required: bool = False
    placeholder: str | None = None
    role: str | None = None
    accessible_name: str | None = None
    text: str | None = None
    test_id: str | None = None
    visible: bool = True


class CaptureResponse(BaseModel):
    final_url: str
    title: str
    screenshot_png_b64: str
    vision_png_b64: str
    aria_snapshot: str
    elements: list[DomElement]
