"""Step 2: the UI-analysis agent (vision model) describes the page's UI contract from the
screenshot plus the captured DOM elements."""

from __future__ import annotations

import base64
from typing import Any

from rag_backend.agents import artifacts, clients
from rag_backend.agents.checks import raise_on_errors, ui_analysis_checks
from rag_backend.agents.llm_json import call_structured, prompt_json
from rag_backend.agents.prompts import UI_ANALYSIS_SYSTEM
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import CaptureResult, UiAnalysis
from rag_backend.config import settings
from rag_backend.exceptions import AgentHandoffError

STEP = "step2_ui_analysis"


def _load_image(ctx: AgentContext, capture: CaptureResult) -> str:
    """The vision-sized screenshot named in the page-capture output, as base64."""
    path = artifacts.resolve(ctx.root, capture.vision_image.name)
    if path is None:
        raise AgentHandoffError(f"capture image not found: {capture.vision_image.name}")
    return base64.b64encode(path.read_bytes()).decode()


async def run(ctx: AgentContext, capture: CaptureResult) -> UiAnalysis:
    dom = [element.model_dump(mode="json", exclude_none=True) for element in capture.elements]
    aria = capture.aria_snapshot[: settings.agents_max_dom_chars]
    ctx.begin(
        STEP,
        {
            "image": capture.vision_image.model_dump(),
            "page_url": capture.final_url,
            "page_title": capture.title,
            "dom_elements": dom,
            "aria_snapshot": aria,
        },
    )
    image_b64 = _load_image(ctx, capture)
    user_content = (
        f"Page URL: {capture.final_url}\nPage title: {capture.title}\n\n"
        f"DOM elements (JSON):\n{prompt_json(dom)}\n\n"
        f"Accessibility snapshot:\n{aria}\n\n"
        "The screenshot of the page is attached."
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": UI_ANALYSIS_SYSTEM},
        {"role": "user", "content": user_content, "images": [image_b64]},
    ]
    ui = await call_structured(ctx, STEP, clients.vision_client, messages, UiAnalysis)
    checks = ui_analysis_checks(ui, capture.elements)
    ctx.finish(STEP, ui.model_dump(mode="json"), [c.model_dump() for c in checks])
    raise_on_errors(STEP, checks)
    return ui
