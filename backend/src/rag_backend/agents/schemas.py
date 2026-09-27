"""Input/output contracts of every agent in the Agents pipeline.

Each agent's LLM output is validated against one of these models (see llm_json.py), and
the validated model, not the raw text, is what the next agent receives. The step DSL
(Locator / TestStep) is shared with the test-runner container (test-runner/models.py):
keep the two in sync.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
_NEEDS_LOCATOR: frozenset[str] = frozenset(
    {"fill", "click", "expect_visible", "expect_hidden", "expect_text", "expect_value"}
)
_NEEDS_VALUE: frozenset[str] = frozenset({"fill", "expect_text", "expect_value", "expect_url"})


class CheckResult(BaseModel):
    """One deterministic contract check on an agent's input or output."""

    name: str
    passed: bool
    severity: Literal["error", "warning"] = "warning"
    detail: str = ""


class ArtifactRef(BaseModel):
    """A file saved in the run folder (screenshot, evidence, generated spec), referenced
    from the JSON log instead of being inlined as base64."""

    # Path relative to the run folder, e.g. "test-cases/TC-REG-001/evidence/step-01-goto.png".
    name: str
    bytes: int
    sha256: str


# --- Step DSL (shared with test-runner) ---


class Locator(BaseModel):
    strategy: LocatorStrategy
    value: str
    # Accessible name; only used with strategy="role".
    name: str | None = None
    exact: bool = False


class TestStep(BaseModel):
    __test__ = False  # not a pytest test class, despite the name

    action: StepAction
    locator: Locator | None = None
    value: str | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> TestStep:
        if self.action in _NEEDS_LOCATOR and self.locator is None:
            raise ValueError(f"action '{self.action}' requires a locator")
        if self.action in ("goto", "expect_url") and self.locator is not None:
            raise ValueError(f"action '{self.action}' must not have a locator")
        if self.action in _NEEDS_VALUE and self.value is None:
            raise ValueError(f"action '{self.action}' requires a value")
        return self


# --- Step 1: page capture ---


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
    # Filled in by the backend (locators.suggest_locator), not by the runner.
    suggested_locator: Locator | None = None


class CaptureResult(BaseModel):
    final_url: str
    title: str
    screenshot: ArtifactRef
    # The (downscaled) image actually sent to the vision model.
    vision_image: ArtifactRef
    aria_snapshot: str
    elements: list[DomElement]


# --- Step 2: UI analysis (vision agent) ---


class UiElement(BaseModel):
    element_id: str = Field(description="DOM id, or a short slug when the element has none")
    type: str = Field(description="textbox, button, heading, alert, status, form, ...")
    label: str = Field(description="Visible label or text, as shown on the screenshot")
    required: bool = False
    locator: Locator
    source: Literal["observed", "inferred"] = "observed"


class UiAnalysis(BaseModel):
    page_title: str
    purpose: str
    elements: list[UiElement]
    messages: list[str] = Field(
        default_factory=list, description="Visible or hidden messages/banners on the page"
    )
    navigation: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


# --- Step 3: business rules ---


class BusinessRule(BaseModel):
    rule_id: str = Field(description="BR-001, BR-002, ...")
    title: str
    description: str
    field: str | None = Field(default=None, description="UI element_id the rule applies to")
    type: Literal["validation", "behaviour", "navigation", "message"]
    source_quote: str = Field(description="Exact sentence from the requirement text")


class BusinessRules(BaseModel):
    rules: list[BusinessRule]


# --- Step 4: test design ---


class TestCase(BaseModel):
    __test__ = False  # not a pytest test class, despite the name

    case_id: str = Field(description="TC-REG-001, TC-REG-002, ...")
    title: str
    priority: Literal["high", "medium", "low"] = "medium"
    type: Literal["positive", "negative", "boundary", "navigation", "ui"] = "positive"
    preconditions: str = ""
    test_data: dict[str, str] = Field(default_factory=dict)
    steps: list[TestStep]
    expected: str
    source_rule_ids: list[str]
    automation_candidate: bool = True


class TestDesign(BaseModel):
    __test__ = False  # not a pytest test class, despite the name

    cases: list[TestCase]


# --- Step 5: business confirmation ---


class CaseVerdict(BaseModel):
    case_id: str
    verdict: Literal["approved", "rejected"]
    reason: str
    rule_ids: list[str] = Field(default_factory=list)


class BusinessConfirmation(BaseModel):
    verdicts: list[CaseVerdict]
    uncovered_rule_ids: list[str] = Field(default_factory=list)


# --- Step 6: test automation ---


class StepRunResult(BaseModel):
    index: int
    action: StepAction
    locator: Locator | None = None
    value: str | None = None
    status: Literal["passed", "failed", "skipped"]
    error: str | None = None
    duration_ms: float = 0.0
    # Evidence: what the browser actually showed (text/value/visibility/url) and a
    # screenshot taken right after the step. None for skipped steps.
    observed: str | None = None
    # Every message visible on the page right after the step (alerts, status banner),
    # e.g. "firstName-error: First name is required." — what the user saw.
    page_messages: list[str] = Field(default_factory=list)
    evidence: ArtifactRef | None = None


class CaseRunResult(BaseModel):
    case_id: str
    status: Literal["passed", "failed", "error"]
    duration_ms: float
    steps: list[StepRunResult]
    failure_screenshot: ArtifactRef | None = None
    console_errors: list[str] = Field(default_factory=list)


class AutomationInput(BaseModel):
    """What the test-automation agent receives: the cases the business agent approved."""

    base_url: str
    approved_cases: list[TestCase]


class AutomationResult(BaseModel):
    base_url: str
    executed_case_ids: list[str]
    not_automated_case_ids: list[str] = Field(default_factory=list)
    results: list[CaseRunResult]
    spec_ts: ArtifactRef | None = None


# --- Step 7: test validation ---


class FailureAnalysis(BaseModel):
    case_id: str
    suspected_cause: Literal["app_defect", "test_defect", "environment"]
    explanation: str


class ValidationNarrative(BaseModel):
    """The LLM-written part of the report; the numbers are computed by code."""

    summary: str
    failure_analysis: list[FailureAnalysis] = Field(default_factory=list)


class CaseReport(BaseModel):
    case_id: str
    title: str
    status: Literal["passed", "failed", "error", "not_run"]
    source_rule_ids: list[str]
    failed_step: int | None = None
    error: str | None = None


class DroppedCase(BaseModel):
    case_id: str
    title: str
    reason: str


class ValidationReport(BaseModel):
    total: int
    passed: int
    failed: int
    errored: int
    pass_rate: float
    cases: list[CaseReport]
    rule_coverage: dict[str, list[str]]
    rules_verified: list[str]
    uncovered_rules: list[str]
    dropped_cases: list[DroppedCase]
    summary: str
    failure_analysis: list[FailureAnalysis]
