from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from rag_backend.agents import clients, runner_client
from rag_backend.agents.run_store import AgentContext
from rag_backend.auth.models import CurrentUser
from rag_backend.pipeline_logging import StepRecorder
from tests.agents.fakes import TARGET_URL, FakeRunnerClient, ScriptedLlmClient

_USER = CurrentUser(
    id="user-1", username="tester", role="admin", allowed_classifications=frozenset()
)


@dataclass
class AgentFakes:
    vision: ScriptedLlmClient
    text: ScriptedLlmClient
    runner: FakeRunnerClient


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> AgentFakes:
    """Scripted model clients and test-runner, installed where the steps look them up.
    Tests queue responses with fakes.vision._responses / fakes.text._responses."""
    installed = AgentFakes(
        vision=ScriptedLlmClient(model="fake-vision"),
        text=ScriptedLlmClient(model="fake-text"),
        runner=FakeRunnerClient(),
    )
    monkeypatch.setattr(clients, "vision_client", installed.vision)
    monkeypatch.setattr(clients, "agents_text_client", installed.text)
    monkeypatch.setattr(runner_client, "test_runner_client", installed.runner)
    return installed


@pytest.fixture
def ctx() -> AgentContext:
    from rag_backend.agents import run_store

    record = run_store.new_run_record("run-1", _USER, TARGET_URL, "requirement", {})
    return AgentContext(
        run_id="run-1",
        record=record,
        recorder=StepRecorder(logging.getLogger("test"), "agents", record),
    )
