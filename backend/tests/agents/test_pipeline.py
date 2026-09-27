from __future__ import annotations

import json
import re
from typing import Any

import pytest

from rag_backend.agents import handoff, pipeline, run_store, step3_business_rules
from rag_backend.agents.defaults import DEFAULT_REGISTER_REQUIREMENT
from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.exceptions import AgentRunInProgressError, AgentTargetNotAllowedError
from tests.agents.conftest import AgentFakes
from tests.agents.fakes import (
    TARGET_URL,
    confirmation_json,
    design_json,
    email_case,
    narrative_json,
    rules_json,
    ui_analysis_json,
)

_USER = CurrentUser(id="u1", username="tester", role="user", allowed_classifications=frozenset())


def _script_happy_path(fakes: AgentFakes) -> None:
    fakes.vision._responses = [ui_analysis_json()]
    fakes.text._responses = [rules_json(), design_json(), confirmation_json(), narrative_json()]


def _read_log(record: dict[str, Any]) -> dict[str, Any]:
    path = settings.pipeline_log_dir / "agents" / record["log_file_stem"] / "run.json"
    return json.loads(path.read_text(encoding="utf-8"))


async def test_happy_path_logs_every_step_with_input_and_output(fakes: AgentFakes) -> None:
    _script_happy_path(fakes)
    record = pipeline.start_run(_USER, TARGET_URL, DEFAULT_REGISTER_REQUIREMENT)

    await pipeline.run_agents_pipeline(record)

    log = _read_log(record)
    assert log["status"] == "succeeded"
    assert list(log["steps"]) == [
        "step1_capture",
        "step2_ui_analysis",
        "step3_business_rules",
        "step4_test_design",
        "step5_business_confirmation",
        "step6_test_automation",
        "step7_test_validation",
    ]
    for name, step in log["steps"].items():
        assert step["status"] == "succeeded", name
        assert "input" in step and "output" in step, name
        assert "checks" in step, name
    # Each LLM-backed step recorded the exact call it made.
    for name in ("step2_ui_analysis", "step3_business_rules", "step7_test_validation"):
        assert log["steps"][name]["llm_calls"][0]["valid"] is True
    assert log["report"]["total"] == 3
    assert log["report"]["passed"] == 3
    assert log["models"]["vision"]["model"] == "fake-vision"
    assert log["created_by"] == "u1"
    assert pipeline.active_run_id() is None


async def test_output_of_each_agent_is_the_input_of_the_next(fakes: AgentFakes) -> None:
    _script_happy_path(fakes)
    record = pipeline.start_run(_USER, TARGET_URL, DEFAULT_REGISTER_REQUIREMENT)

    await pipeline.run_agents_pipeline(record)

    steps = _read_log(record)["steps"]
    assert steps["step3_business_rules"]["input"]["ui_analysis"] == (
        steps["step2_ui_analysis"]["output"]
    )
    assert steps["step4_test_design"]["input"]["rules"] == steps["step3_business_rules"]["output"]
    assert steps["step5_business_confirmation"]["input"]["cases"] == (
        steps["step4_test_design"]["output"]["cases"]
    )
    assert [c["case_id"] for c in steps["step6_test_automation"]["input"]["approved_cases"]] == [
        "TC-REG-001",
        "TC-REG-002",
        "TC-REG-003",
    ]


async def test_every_agent_writes_input_and_output_files_chained_by_sources(
    fakes: AgentFakes,
) -> None:
    _script_happy_path(fakes)
    record = pipeline.start_run(_USER, TARGET_URL, DEFAULT_REGISTER_REQUIREMENT)

    await pipeline.run_agents_pipeline(record)

    steps = _read_log(record)["steps"]
    task = f"task{record['run_id'][:8]}"
    for name, step in steps.items():
        agent = handoff.agent_of(name)
        for kind in ("input", "output"):
            rel = step["handoff"][kind]
            assert re.fullmatch(rf"{agent}/{kind}/{agent}_{task}_\d{{8}}-\d{{6}}(-\d+)?\.md", rel)
            assert (settings.agents_result_dir / rel).is_file()
    output = {name: step["handoff"]["output"] for name, step in steps.items()}
    assert steps["step2_ui_analysis"]["handoff"]["sources"] == [output["step1_capture"]]
    assert steps["step3_business_rules"]["handoff"]["sources"] == [output["step2_ui_analysis"]]
    assert steps["step5_business_confirmation"]["handoff"]["sources"] == [
        output["step4_test_design"],
        output["step3_business_rules"],
    ]
    assert steps["step7_test_validation"]["handoff"]["sources"][0] == (
        output["step6_test_automation"]
    )
    final = (settings.agents_result_dir / output["step7_test_validation"]).read_text("utf-8")
    assert "## Result: ✅ SUCCESS — 3/3 passed (100%)" in final
    first_input = settings.agents_result_dir / steps["step2_ui_analysis"]["handoff"]["input"]
    assert f"](../../{output['step1_capture']})" in first_input.read_text("utf-8")


async def test_next_agent_input_is_parsed_from_the_previous_output_file(
    fakes: AgentFakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editing an agent's output file on disk changes what the next agent receives:
    the file is the handoff, not a copy of an in-memory value."""
    _script_happy_path(fakes)
    real_rules_step = step3_business_rules.run

    async def rules_then_edit_file(*args: Any, **kwargs: Any) -> Any:
        result = await real_rules_step(*args, **kwargs)
        rel = record["steps"]["step3_business_rules"]["handoff"]["output"]
        path = settings.agents_result_dir / rel
        path.write_text(path.read_text("utf-8").replace("First name required", "EDITED"), "utf-8")
        return result

    monkeypatch.setattr(step3_business_rules, "run", rules_then_edit_file)
    record = pipeline.start_run(_USER, TARGET_URL, DEFAULT_REGISTER_REQUIREMENT)

    await pipeline.run_agents_pipeline(record)

    design_input = _read_log(record)["steps"]["step4_test_design"]["input"]
    titles = [rule["title"] for rule in design_input["rules"]["rules"]]
    assert "EDITED" in titles


async def test_failed_case_output_shows_page_message_and_evidence(fakes: AgentFakes) -> None:
    _script_happy_path(fakes)
    fakes.runner._fail = {"TC-REG-002"}
    record = pipeline.start_run(_USER, TARGET_URL, DEFAULT_REGISTER_REQUIREMENT)

    await pipeline.run_agents_pipeline(record)

    steps = _read_log(record)["steps"]
    automation = settings.agents_result_dir / steps["step6_test_automation"]["handoff"]["output"]
    text = automation.read_text("utf-8")
    assert "## ❌ TC-REG-002 — FAILED" in text
    assert "| Message shown on page |" in text
    assert "❌ failed | firstName-error: First name is required." in text
    files = automation.parent / f"{automation.stem}_files"
    assert f"]({files.name}/test-cases/TC-REG-002/evidence/step-" in text
    assert (files / "test-cases" / "TC-REG-002" / "evidence").is_dir()
    final = settings.agents_result_dir / steps["step7_test_validation"]["handoff"]["output"]
    validation = final.read_text("utf-8")
    assert "- ❌ **TC-REG-002**" in validation
    assert "Page showed: firstName-error: First name is required." in validation
    files_rel = steps["step6_test_automation"]["handoff"]["files"]
    # The failing step's screenshot is embedded, not just linked.
    assert f"![TC-REG-002 — Step 3 · expect_text](../../{files_rel}/test-cases/" in validation
    assert "![TC-REG-001 — Step " in validation


async def test_rejected_case_goes_back_to_design_for_a_second_round(fakes: AgentFakes) -> None:
    fakes.vision._responses = [ui_analysis_json()]
    fakes.text._responses = [
        rules_json(),
        design_json(),
        confirmation_json({"TC-REG-003": "Message text differs from BR-002"}),
        design_json(email_case()),
        confirmation_json(None, "TC-REG-003"),
        narrative_json(),
    ]
    record = pipeline.start_run(_USER, TARGET_URL, DEFAULT_REGISTER_REQUIREMENT)

    await pipeline.run_agents_pipeline(record)

    log = _read_log(record)
    assert log["status"] == "succeeded"
    assert "step4_test_design_r2" in log["steps"]
    feedback = log["steps"]["step4_test_design_r2"]["input"]["feedback"]
    assert feedback["rejected_cases"][0]["reason"] == "Message text differs from BR-002"
    assert [r["rejected"] for r in log["design_rounds"]] == [["TC-REG-003"], []]
    assert log["report"]["total"] == 3
    assert log["report"]["dropped_cases"] == []


async def test_still_rejected_after_last_round_is_dropped_not_executed(
    fakes: AgentFakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agents_max_design_rounds", 1)
    fakes.vision._responses = [ui_analysis_json()]
    fakes.text._responses = [
        rules_json(),
        design_json(),
        confirmation_json({"TC-REG-003": "wrong"}),
        narrative_json(),
    ]
    record = pipeline.start_run(_USER, TARGET_URL, DEFAULT_REGISTER_REQUIREMENT)

    await pipeline.run_agents_pipeline(record)

    log = _read_log(record)
    assert [d["case_id"] for d in log["report"]["dropped_cases"]] == ["TC-REG-003"]
    executed = log["steps"]["step6_test_automation"]["output"]["executed_case_ids"]
    assert "TC-REG-003" not in executed


async def test_failure_mid_run_keeps_earlier_steps_and_marks_failing_step(
    fakes: AgentFakes,
) -> None:
    fakes.vision._responses = [ui_analysis_json()]
    fakes.text._responses = ["not json", "still not json"]
    record = pipeline.start_run(_USER, TARGET_URL, DEFAULT_REGISTER_REQUIREMENT)

    await pipeline.run_agents_pipeline(record)

    log = _read_log(record)
    assert log["status"] == "failed"
    assert "AgentOutputValidationError" in log["error"]
    assert log["steps"]["step2_ui_analysis"]["status"] == "succeeded"
    failed = log["steps"]["step3_business_rules"]
    assert failed["status"] == "failed"
    assert len(failed["llm_calls"]) == 2
    assert "step4_test_design" not in log["steps"]
    # The failed agent still gets an output file saying why the chain stopped there.
    output = (settings.agents_result_dir / failed["handoff"]["output"]).read_text("utf-8")
    assert "## Result: ❌ FAILED — AgentOutputValidationError" in output
    assert "| 2 | 1 | ollama/fake-text |" in output
    assert pipeline.active_run_id() is None


def test_only_one_run_at_a_time(fakes: AgentFakes) -> None:
    pipeline.start_run(_USER, TARGET_URL, "req")

    with pytest.raises(AgentRunInProgressError):
        pipeline.start_run(_USER, TARGET_URL, "req")


@pytest.mark.parametrize(
    "url",
    [
        "http://backend:8000/documents",
        "http://169.254.169.254/latest",
        "file:///etc/passwd",
        "myweb:8080",
    ],
)
def test_targets_outside_the_allow_list_are_rejected(url: str) -> None:
    with pytest.raises(AgentTargetNotAllowedError):
        pipeline.start_run(_USER, url, "req")


def test_run_that_stopped_updating_is_reported_as_stale(fakes: AgentFakes) -> None:
    record = pipeline.start_run(_USER, TARGET_URL, "req")
    record["status"] = "running"
    assert run_store.effective_status(record) == "running"

    record["updated_at"] = "2020-01-01T00:00:00+00:00"

    assert run_store.effective_status(record) == "stale"


def test_run_interrupted_by_a_restart_is_stale_and_does_not_block(fakes: AgentFakes) -> None:
    record = pipeline.start_run(_USER, TARGET_URL, "req")
    record["status"] = "running"
    run_store.set_active_run(None)  # what a fresh backend process sees

    assert run_store.effective_status(record) == "stale"
    pipeline.start_run(_USER, TARGET_URL, "req")  # no AgentRunInProgressError
