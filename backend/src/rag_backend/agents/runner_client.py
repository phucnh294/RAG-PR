"""HTTP client for the test-runner container (headless Chromium + Playwright)."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from rag_backend.agents.schemas import DomElement, StepRunResult, TestStep
from rag_backend.config import settings
from rag_backend.exceptions import TestRunnerError


class RunnerCapture(BaseModel):
    final_url: str
    title: str
    screenshot_png_b64: str
    # Downscaled copy for the vision model; older runners don't send it.
    vision_png_b64: str | None = None
    aria_snapshot: str
    elements: list[DomElement]


class RunnerCase(BaseModel):
    case_id: str
    title: str = ""
    steps: list[TestStep]


class RunnerStepResult(StepRunResult):
    """A step result as the runner sends it: the evidence screenshot is still base64
    (step 6 saves it as a file and keeps only the ArtifactRef)."""

    screenshot_png_b64: str | None = None


class RunnerCaseResult(BaseModel):
    case_id: str
    status: str
    duration_ms: float
    steps: list[RunnerStepResult]
    failure_screenshot_png_b64: str | None = None
    console_errors: list[str] = []


class RunnerRunResponse(BaseModel):
    cases: list[RunnerCaseResult]


class TestRunnerClient:
    __test__ = False  # not a pytest test class, despite the name

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url or settings.test_runner_base_url
        self._timeout_seconds = timeout_seconds or settings.test_runner_timeout_seconds
        self._transport = transport

    async def capture(self, url: str) -> RunnerCapture:
        body = await self._post(
            "/capture", {"url": url, "vision_max_width": settings.agents_vision_max_width}
        )
        return _parse(RunnerCapture, body, "capture")

    async def run(self, base_url: str, cases: list[RunnerCase]) -> RunnerRunResponse:
        payload = {
            "base_url": base_url,
            "cases": [case.model_dump(mode="json") for case in cases],
            "default_timeout_ms": settings.test_runner_step_timeout_ms,
            "capture_evidence": settings.agents_capture_evidence,
        }
        body = await self._post("/run", payload)
        return _parse(RunnerRunResponse, body, "run")

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        timeout = httpx.Timeout(self._timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                response = await client.post(f"{self._base_url}{path}", json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as error:
            detail = error.response.text[:300]
            raise TestRunnerError(
                f"test-runner {path} failed: HTTP {error.response.status_code} {detail}"
            ) from error
        except httpx.HTTPError as error:
            raise TestRunnerError(
                f"test-runner {path} failed: {type(error).__name__} {error}".rstrip()
            ) from error
        except ValueError as error:
            raise TestRunnerError(f"test-runner {path} returned non-JSON") from error


def _parse[ModelT: BaseModel](model: type[ModelT], body: Any, what: str) -> ModelT:
    try:
        return model.model_validate(body)
    except ValidationError as error:
        raise TestRunnerError(f"Malformed test-runner {what} response: {error}") from error


test_runner_client = TestRunnerClient()
