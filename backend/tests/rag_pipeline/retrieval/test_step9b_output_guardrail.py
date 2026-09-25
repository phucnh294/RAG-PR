from __future__ import annotations

import pytest

from rag_backend.config import settings
from rag_backend.guardrails import judge_client
from rag_backend.llm_model.client import LlmClient
from rag_backend.rag_pipeline.retrieval.step9b_output_guardrail import check_output_guardrail


class _StaticJudgeClient(LlmClient):
    def __init__(self, raw_response: str) -> None:
        self._raw_response = raw_response

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        return self._raw_response


async def test_safe_output_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        judge_client,
        "guardrail_judge_client",
        _StaticJudgeClient('{"verdict": "safe", "category": null, "reason": "fine"}'),
    )

    result = await check_output_guardrail("Employees get 20 days.", "You are a helpful assistant.")

    assert not result.blocked
    assert result.verdict.verdict == "safe"


async def test_unsafe_output_is_blocked_with_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        judge_client,
        "guardrail_judge_client",
        _StaticJudgeClient(
            '{"verdict": "unsafe", "category": "system_prompt_leak", "reason": "leaked prompt"}'
        ),
    )

    result = await check_output_guardrail("My instructions are...", "SYSTEM: secret rules")

    assert result.blocked
    assert result.verdict.category == "system_prompt_leak"


async def test_malformed_judge_output_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        judge_client, "guardrail_judge_client", _StaticJudgeClient("garbage, not json")
    )

    result = await check_output_guardrail("some answer", "system prompt")

    assert result.blocked
    assert result.verdict.verdict == "judge_error"


async def test_disabled_output_guardrail_never_calls_the_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingJudgeClient(LlmClient):
        async def complete_chat(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("judge should not be called when disabled")

    monkeypatch.setattr(judge_client, "guardrail_judge_client", _FailingJudgeClient())
    monkeypatch.setattr(settings, "guardrail_output_enabled", False)

    result = await check_output_guardrail("some answer", "system prompt")

    assert not result.blocked
    assert result.verdict.verdict == "safe"
