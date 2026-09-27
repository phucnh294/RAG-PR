from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from rag_backend.agents import handoff
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import BusinessRules
from rag_backend.config import settings
from rag_backend.exceptions import AgentHandoffError
from tests.agents.fakes import rules_json


def _rules_payload() -> dict[str, object]:
    return BusinessRules.model_validate_json(rules_json()).model_dump(mode="json")


def test_output_file_round_trips_its_payload(ctx: AgentContext) -> None:
    ctx.begin("step3_business_rules", {"requirement": "Req", "ui_analysis": {"elements": []}})
    ctx.finish("step3_business_rules", _rules_payload(), [])

    rules = handoff.read_output(ctx.record, "step3_business_rules", BusinessRules)

    assert rules.model_dump(mode="json") == _rules_payload()
    rel = ctx.record["steps"]["step3_business_rules"]["handoff"]["output"]
    assert re.fullmatch(r"business-analysis/output/business-analysis_taskrun1_\d{8}-\d{6}\.md", rel)
    text = (settings.agents_result_dir / rel).read_text("utf-8")
    assert "## Result: ✅ SUCCESS — 3 business rule(s) extracted" in text
    assert "| BR-001 | validation | firstName | First name required |" in text


def test_same_second_files_get_a_numbered_suffix(
    ctx: AgentContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FrozenClock:
        @staticmethod
        def now(tz: object = None) -> datetime:
            return datetime(2026, 9, 26, 10, 15, 30, tzinfo=UTC)

    monkeypatch.setattr(handoff, "datetime", _FrozenClock)

    first = handoff.write_input(ctx.record, "step3_business_rules", {})
    second = handoff.write_input(ctx.record, "step5_business_confirmation", {})

    assert first == "business-analysis/input/business-analysis_taskrun1_20260926-101530.md"
    assert second == "business-analysis/input/business-analysis_taskrun1_20260926-101530-2.md"


def test_rewriting_an_output_keeps_its_file_name(ctx: AgentContext) -> None:
    ctx.begin("step3_business_rules", {"requirement": "Req"})
    ctx.finish("step3_business_rules", _rules_payload(), [])
    rel = ctx.record["steps"]["step3_business_rules"]["handoff"]["output"]

    ctx.fail("step3_business_rules", "AgentsError: rules check failed")

    assert ctx.record["steps"]["step3_business_rules"]["handoff"]["output"] == rel
    text = (settings.agents_result_dir / rel).read_text("utf-8")
    assert "## Result: ❌ FAILED — AgentsError: rules check failed" in text


def test_corrupt_or_wrong_payload_raises_handoff_error(ctx: AgentContext) -> None:
    ctx.begin("step3_business_rules", {"requirement": "Req"})
    ctx.finish("step3_business_rules", _rules_payload(), [])
    path = (
        settings.agents_result_dir
        / ctx.record["steps"]["step3_business_rules"]["handoff"]["output"]
    )

    path.write_text(path.read_text("utf-8").replace('"rules"', '"rulez"'), "utf-8")
    with pytest.raises(AgentHandoffError, match="not a valid BusinessRules"):
        handoff.read_output(ctx.record, "step3_business_rules", BusinessRules)

    path.write_text("no json here", "utf-8")
    with pytest.raises(AgentHandoffError, match="no handoff JSON block"):
        handoff.read_output(ctx.record, "step3_business_rules", BusinessRules)


def test_reading_a_step_that_never_ran_raises(ctx: AgentContext) -> None:
    with pytest.raises(AgentHandoffError, match="has no output file"):
        handoff.read_output(ctx.record, "step3_business_rules", BusinessRules)


def test_resolve_stays_inside_the_results_folder() -> None:
    assert handoff.resolve("../pipeline-logs/secret.md") is None
    assert handoff.resolve("ui-analysis/output/missing.md") is None


def test_second_design_round_is_built_from_the_first_rounds_verdicts(
    ctx: AgentContext,
) -> None:
    for step in ("step1_capture", "step2_ui_analysis", "step3_business_rules"):
        ctx.begin(step, {})
        ctx.finish(step, {}, [])
    ctx.begin("step4_test_design", {})
    ctx.finish("step4_test_design", {"cases": []}, [])
    ctx.begin("step5_business_confirmation", {})
    ctx.finish("step5_business_confirmation", {"verdicts": []}, [])

    sources = handoff.sources_for(ctx.record, "step4_test_design_r2")

    outputs = {name: step["handoff"]["output"] for name, step in ctx.record["steps"].items()}
    assert sources == [
        outputs["step3_business_rules"],
        outputs["step2_ui_analysis"],
        outputs["step1_capture"],
        outputs["step5_business_confirmation"],
    ]
