from __future__ import annotations

import json

import httpx
import pytest

from rag_backend.agents.runner_client import RunnerCase, TestRunnerClient
from rag_backend.agents.schemas import TestStep
from rag_backend.exceptions import TestRunnerError
from tests.agents.fakes import PNG_B64


def _client(handler) -> TestRunnerClient:  # type: ignore[no-untyped-def]
    return TestRunnerClient(base_url="http://runner", transport=httpx.MockTransport(handler))


async def test_capture_posts_url_and_parses_response() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "final_url": "http://myweb:8080/myweb/",
                "title": "Register Account",
                "screenshot_png_b64": PNG_B64,
                "aria_snapshot": "- heading",
                "elements": [{"tag": "input", "id": "email", "required": True}],
            },
        )

    capture = await _client(handler).capture("http://myweb:8080/myweb")

    assert str(seen[0].url) == "http://runner/capture"
    assert json.loads(seen[0].content) == {
        "url": "http://myweb:8080/myweb",
        "vision_max_width": 640,
    }
    assert capture.elements[0].required is True


async def test_run_sends_step_dsl_json() -> None:
    bodies: list[dict] = []  # type: ignore[type-arg]

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"cases": []})

    case = RunnerCase(case_id="TC-1", steps=[TestStep(action="goto", value="")])
    await _client(handler).run("http://myweb:8080/myweb/", [case])

    sent = bodies[0]
    assert sent["base_url"] == "http://myweb:8080/myweb/"
    assert sent["cases"][0]["steps"][0] == {"action": "goto", "locator": None, "value": ""}
    assert sent["default_timeout_ms"] > 0


async def test_http_error_becomes_test_runner_error() -> None:
    client = _client(lambda request: httpx.Response(502, text="Could not load page"))

    with pytest.raises(TestRunnerError, match="502"):
        await client.capture("http://myweb:8080/myweb/")


async def test_malformed_response_becomes_test_runner_error() -> None:
    client = _client(lambda request: httpx.Response(200, json={"unexpected": True}))

    with pytest.raises(TestRunnerError, match="Malformed"):
        await client.capture("http://myweb:8080/myweb/")
