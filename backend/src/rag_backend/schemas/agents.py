from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    target_url: str = Field(min_length=1, max_length=500)
    # Kept well inside agents_num_ctx: the requirement is resent to four agents.
    requirement: str = Field(min_length=1, max_length=8000)


class AgentRunStarted(BaseModel):
    run_id: str
    status: str


class AgentModelInfo(BaseModel):
    provider: str
    model: str


class AgentDefaults(BaseModel):
    target_url: str
    requirement: str
    allowed_target_hosts: list[str]
    models: dict[str, AgentModelInfo]
    max_design_rounds: int
    active_run_id: str | None = None


class AgentStepStatus(BaseModel):
    name: str
    status: str
    duration_ms: float | None = None


class AgentRunSummary(BaseModel):
    run_id: str
    status: str
    created_at: str
    finished_at: str | None = None
    username: str | None = None
    target_url: str
    current_step: str | None = None
    error: str | None = None
    passed: int | None = None
    total: int | None = None
    steps: list[AgentStepStatus]


class AgentRunDetail(BaseModel):
    run_id: str
    status: str
    record: dict[str, Any]
