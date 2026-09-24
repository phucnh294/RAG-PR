from __future__ import annotations

import pytest

from rag_backend.exceptions import GuardrailJudgeError
from rag_backend.guardrails import judge_client
from rag_backend.llm_model.client import LlmClient, LlmClientError


class _StaticJudgeClient(LlmClient):
    def __init__(self, raw_response: str) -> None:
        self._raw_response = raw_response

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        return self._raw_response


class _FailingJudgeClient(LlmClient):
    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        raise LlmClientError("boom")


async def test_judge_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        judge_client,
        "guardrail_judge_client",
        _StaticJudgeClient('{"verdict": "safe", "category": null, "reason": "ok"}'),
    )

    verdict = await judge_client.judge("hello", layer="input")

    assert verdict.verdict == "safe"


async def test_judge_llm_client_error_fails_closed_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(judge_client, "guardrail_judge_client", _FailingJudgeClient())

    verdict = await judge_client.judge("hello", layer="output")

    assert verdict.verdict == "judge_error"


async def test_judge_guardrail_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RaisesGuardrailError(LlmClient):
        async def complete_chat(self, messages: list[dict[str, str]]) -> str:
            raise GuardrailJudgeError("unreachable")

    monkeypatch.setattr(judge_client, "guardrail_judge_client", _RaisesGuardrailError())

    verdict = await judge_client.judge("hello", layer="input")

    assert verdict.verdict == "judge_error"
