from __future__ import annotations

import base64
import json

import pytest

from rag_backend.agents import handoff, step1_capture
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import CaptureResult
from rag_backend.exceptions import AgentsError
from tests.agents.conftest import AgentFakes
from tests.agents.fakes import PNG_B64, TARGET_URL, FakeRunnerClient


async def test_capture_logs_target_as_input_and_saves_screenshot_as_artifact(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    await step1_capture.run(ctx, TARGET_URL)

    step = ctx.record["steps"]["step1_capture"]
    assert fakes.runner.captured == [TARGET_URL]
    assert step["input"] == {"target_url": TARGET_URL}
    assert step["status"] == "succeeded"
    # The log references the PNG; it never inlines the base64.
    assert PNG_B64 not in json.dumps(ctx.record)
    assert step["output"]["screenshot"]["name"] == "capture/capture.png"
    assert step["output"]["vision_image"]["name"] == "capture/capture_vision.png"
    assert (ctx.root / "capture/capture_vision.png").read_bytes() == base64.b64decode(PNG_B64)
    assert all(check["passed"] for check in step["checks"])


async def test_capture_writes_page_capture_input_and_output_files(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    await step1_capture.run(ctx, TARGET_URL)

    files = ctx.record["steps"]["step1_capture"]["handoff"]
    assert files["input"].startswith("page-capture/input/page-capture_taskrun1_")
    output = handoff.resolve(files["output"])
    assert output is not None
    text = output.read_text(encoding="utf-8")
    assert "## Result: ✅ SUCCESS — page 'Register Account' loaded" in text
    # The screenshot is copied next to the output, so the .md renders on its own.
    assert "![Page screenshot](" in text
    assert (output.parent / f"{output.stem}_files" / "capture" / "capture.png").is_file()
    capture = handoff.read_output(ctx.record, "step1_capture", CaptureResult)
    assert capture.title == "Register Account"


async def test_capture_adds_suggested_locators_to_elements(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    capture = await step1_capture.run(ctx, TARGET_URL)

    first_name = next(e for e in capture.elements if e.id == "firstName")
    assert first_name.suggested_locator is not None
    assert first_name.suggested_locator.value == "First name"


async def test_capture_without_elements_fails_the_step(
    ctx: AgentContext, fakes: AgentFakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rag_backend.agents import runner_client

    monkeypatch.setattr(runner_client, "test_runner_client", FakeRunnerClient(elements=[]))

    with pytest.raises(AgentsError, match="has_elements"):
        await step1_capture.run(ctx, TARGET_URL)

    checks = ctx.record["steps"]["step1_capture"]["checks"]
    assert any(c["name"] == "has_elements" and not c["passed"] for c in checks)
