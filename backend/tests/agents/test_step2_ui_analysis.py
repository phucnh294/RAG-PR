from __future__ import annotations

import json

from rag_backend.agents import step1_capture, step2_ui_analysis
from rag_backend.agents.run_store import AgentContext
from tests.agents.conftest import AgentFakes
from tests.agents.fakes import PNG_B64, TARGET_URL, ui_analysis_json


def _checks(ctx: AgentContext) -> dict[str, bool]:
    return {c["name"]: c["passed"] for c in ctx.record["steps"]["step2_ui_analysis"]["checks"]}


async def test_vision_agent_receives_screenshot_and_dom(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    capture = await step1_capture.run(ctx, TARGET_URL)
    fakes.vision._responses = [ui_analysis_json()]

    ui = await step2_ui_analysis.run(ctx, capture)

    sent = fakes.vision.calls[0]["messages"]
    assert sent[-1]["images"] == [PNG_B64]
    assert '"firstName"' in sent[-1]["content"]
    step = ctx.record["steps"]["step2_ui_analysis"]
    # The log names exactly the image the model received (the vision-sized copy).
    assert step["input"]["image"] == capture.vision_image.model_dump()
    assert [e["id"] for e in step["input"]["dom_elements"] if e["tag"] == "input"] == [
        "firstName",
        "lastName",
        "dob",
        "email",
    ]
    assert step["output"]["page_title"] == ui.page_title == "Register Account"
    assert _checks(ctx) == {
        "has_elements": True,
        "observed_elements_exist_in_dom": True,
        "required_flags_match_dom": True,
        "all_form_fields_reported": True,
    }


async def test_hallucinated_element_and_wrong_required_flag_are_flagged(
    ctx: AgentContext, fakes: AgentFakes
) -> None:
    capture = await step1_capture.run(ctx, TARGET_URL)
    answer = json.loads(ui_analysis_json())
    answer["elements"][2]["required"] = True  # dob is optional in the DOM
    answer["elements"].append(
        {
            "element_id": "phone",
            "type": "textbox",
            "label": "Phone",
            "locator": {"strategy": "label", "value": "Phone"},
            "source": "observed",
        }
    )
    fakes.vision._responses = [json.dumps(answer)]

    await step2_ui_analysis.run(ctx, capture)

    checks = _checks(ctx)
    assert checks["observed_elements_exist_in_dom"] is False
    assert checks["required_flags_match_dom"] is False
