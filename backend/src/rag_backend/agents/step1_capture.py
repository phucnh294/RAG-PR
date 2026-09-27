"""Step 1: load the target page in the test-runner's browser and capture what the agents
will analyse — a screenshot, the accessibility snapshot and the interactive elements."""

from __future__ import annotations

from urllib.parse import urlparse

from rag_backend.agents import artifacts, runner_client
from rag_backend.agents.checks import check, raise_on_errors
from rag_backend.agents.locators import with_suggested_locators
from rag_backend.agents.run_layout import CAPTURE_FOLDER
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import CaptureResult

STEP = "step1_capture"


async def run(ctx: AgentContext, target_url: str) -> CaptureResult:
    """The capture, with its screenshots saved under capture/ in the run folder. The
    vision agent loads capture_vision.png from the path in the capture output."""
    ctx.begin(STEP, {"target_url": target_url})
    raw = await runner_client.test_runner_client.capture(target_url)
    folder = CAPTURE_FOLDER
    screenshot = artifacts.save_png_b64(ctx.root, f"{folder}/capture.png", raw.screenshot_png_b64)
    vision_b64 = raw.vision_png_b64 or raw.screenshot_png_b64
    vision_image = artifacts.save_png_b64(ctx.root, f"{folder}/capture_vision.png", vision_b64)
    capture = CaptureResult(
        final_url=raw.final_url,
        title=raw.title,
        screenshot=screenshot,
        vision_image=vision_image,
        aria_snapshot=raw.aria_snapshot,
        elements=with_suggested_locators(raw.elements),
    )
    checks = [
        check("page_loaded", bool(raw.title), f"title={raw.title!r}", "error"),
        check("has_elements", bool(raw.elements), f"{len(raw.elements)} element(s)", "error"),
        check(
            "stayed_on_target_host",
            urlparse(raw.final_url).hostname == urlparse(target_url).hostname,
            f"final_url={raw.final_url}",
        ),
    ]
    ctx.finish(STEP, capture.model_dump(mode="json"), [c.model_dump() for c in checks])
    raise_on_errors(STEP, checks)
    return capture
