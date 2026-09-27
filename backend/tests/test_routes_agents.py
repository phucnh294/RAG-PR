from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_backend.agents import clients, runner_client
from rag_backend.agents.defaults import DEFAULT_REGISTER_REQUIREMENT
from tests.agents.fakes import (
    TARGET_URL,
    FakeRunnerClient,
    ScriptedLlmClient,
    confirmation_json,
    design_json,
    narrative_json,
    rules_json,
    ui_analysis_json,
)


@pytest.fixture
def scripted_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clients, "vision_client", ScriptedLlmClient([ui_analysis_json()]))
    monkeypatch.setattr(
        clients,
        "agents_text_client",
        ScriptedLlmClient([rules_json(), design_json(), confirmation_json(), narrative_json()]),
    )
    monkeypatch.setattr(runner_client, "test_runner_client", FakeRunnerClient())


def _start(client: TestClient, **headers: str) -> str:
    response = client.post(
        "/agents/runs",
        json={"target_url": TARGET_URL, "requirement": DEFAULT_REGISTER_REQUIREMENT},
        headers=headers or None,
    )
    assert response.status_code == 202, response.text
    return str(response.json()["run_id"])


def test_defaults_return_seeded_requirement_and_target(client: TestClient) -> None:
    body = client.get("/agents/defaults").json()

    assert body["requirement"] == DEFAULT_REGISTER_REQUIREMENT
    assert body["target_url"] == TARGET_URL
    assert set(body["models"]) == {"vision", "text"}


def test_run_executes_in_background_and_full_record_is_readable(
    client: TestClient, scripted_agents: None
) -> None:
    run_id = _start(client)

    detail = client.get(f"/agents/runs/{run_id}").json()

    assert detail["status"] == "succeeded"
    assert "step7_test_validation" in detail["record"]["steps"]
    runs = client.get("/agents/runs").json()
    assert runs[0]["run_id"] == run_id
    assert runs[0]["passed"] == runs[0]["total"] == 3
    assert [s["status"] for s in runs[0]["steps"]] == ["succeeded"] * 7


def test_artifacts_are_served_and_names_are_validated(
    client: TestClient, scripted_agents: None
) -> None:
    run_id = _start(client)
    record = client.get(f"/agents/runs/{run_id}").json()["record"]
    screenshot = record["steps"]["step1_capture"]["output"]["screenshot"]["name"]
    spec = record["steps"]["step6_test_automation"]["output"]["spec_ts"]["name"]

    png = client.get(f"/agents/runs/{run_id}/artifacts/{screenshot}")
    ts = client.get(f"/agents/runs/{run_id}/artifacts/{spec}")

    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert "@playwright/test" in ts.text
    base = f"/agents/runs/{run_id}/artifacts"
    assert client.get(f"{base}/..%2F..%2Fsecret.png").status_code == 404
    assert client.get(f"{base}/agents/../../../secret.png").status_code == 404
    assert client.get(f"{base}/README.exe").status_code == 404
    assert client.get(f"{base}/missing/file.png").status_code == 404


def test_run_folder_has_agent_folders_test_case_docs_and_evidence(
    client: TestClient, scripted_agents: None
) -> None:
    run_id = _start(client)
    record = client.get(f"/agents/runs/{run_id}").json()["record"]
    base = f"/agents/runs/{run_id}/artifacts"

    # One folder per test case: Markdown doc with the evidence table, raw result, screenshots.
    assert [case["case_id"] for case in record["test_cases"]] == [
        "TC-REG-001",
        "TC-REG-002",
        "TC-REG-003",
    ]
    doc = client.get(f"{base}/test-cases/TC-REG-001/test-case.md").text
    assert "# TC-REG-001 — Successful registration" in doc
    assert "✅ PASSED" in doc
    assert "**BR-003**" in doc
    assert "[screenshot](evidence/step-01-goto.png)" in doc
    evidence = client.get(f"{base}/test-cases/TC-REG-001/evidence/step-01-goto.png")
    assert evidence.headers["content-type"] == "image/png"
    result = client.get(f"{base}/test-cases/TC-REG-001/result.json").json()
    assert result["status"] == "passed"

    readme = client.get(f"{base}/README.md").text
    assert "[TC-REG-002](test-cases/TC-REG-002/test-case.md)" in readme
    assert "`business-analysis/output/business-analysis_task" in readme


def test_handoff_files_are_served_only_for_the_run_that_wrote_them(
    client: TestClient, scripted_agents: None
) -> None:
    run_id = _start(client)
    record = client.get(f"/agents/runs/{run_id}").json()["record"]
    base = f"/agents/runs/{run_id}/handoff"
    steps = record["steps"]

    rules_input = client.get(f"{base}/{steps['step3_business_rules']['handoff']['input']}")
    assert rules_input.status_code == 200
    assert rules_input.headers["content-type"].startswith("text/markdown")
    assert "## Requirement text" in rules_input.text
    final = client.get(f"{base}/{steps['step7_test_validation']['handoff']['output']}").text
    assert "## Result: ✅ SUCCESS — 3/3 passed (100%)" in final
    evidence_folder = steps["step6_test_automation"]["handoff"]["files"]
    shot = client.get(f"{base}/{evidence_folder}/test-cases/TC-REG-001/evidence/step-01-goto.png")
    assert shot.headers["content-type"] == "image/png"

    assert client.get(f"{base}/ui-analysis/output/other-run.md").status_code == 404
    assert client.get(f"{base}/..%2F..%2Fsecret.md").status_code == 404
    assert client.get(f"{base}/{evidence_folder}/../../../x.md").status_code == 404


def test_disallowed_target_is_rejected_with_400(client: TestClient) -> None:
    response = client.post(
        "/agents/runs", json={"target_url": "http://postgres:5432/", "requirement": "x"}
    )

    assert response.status_code == 400
    assert "not an allowed target" in response.json()["detail"]


def test_second_run_while_one_is_active_returns_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rag_backend.agents import run_store

    monkeypatch.setattr(run_store, "_active_run_id", "other-run")

    response = client.post("/agents/runs", json={"target_url": TARGET_URL, "requirement": "x"})

    assert response.status_code == 409


def test_other_users_cannot_see_a_run(
    client: TestClient, scripted_agents: None, role_headers: dict[str, dict[str, str]]
) -> None:
    run_id = _start(client)

    response = client.get(f"/agents/runs/{run_id}", headers=role_headers["user"])

    assert response.status_code == 404
    assert client.get("/agents/runs", headers=role_headers["user"]).json() == []


def test_agents_runs_appear_in_logs_tab(client: TestClient, scripted_agents: None) -> None:
    _start(client)

    logs = client.get("/logs", params={"pipeline": "agents"}).json()

    assert len(logs) == 1
    assert "succeeded (3/3 passed)" in logs[0]["summary"]
    detail = client.get(f"/logs/agents/{logs[0]['id']}").json()
    assert detail["record"]["pipeline"] == "agents"


def test_agents_routes_require_a_user(client: TestClient) -> None:
    response = client.get("/agents/runs", headers={"X-User-Id": ""})

    assert response.status_code == 401
