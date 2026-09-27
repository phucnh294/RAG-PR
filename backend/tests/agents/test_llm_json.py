from __future__ import annotations

import httpx
import pytest

from rag_backend.agents.llm_json import (
    call_structured,
    extract_json,
    is_transient,
    loggable_messages,
)
from rag_backend.agents.run_store import AgentContext
from rag_backend.agents.schemas import BusinessRules
from rag_backend.config import settings
from rag_backend.exceptions import AgentOutputValidationError
from rag_backend.llm_model.client import LlmClientError
from tests.agents.fakes import PNG_B64, ScriptedLlmClient, rules_json

_STEP = "step3_business_rules"


def test_extract_json_tolerates_code_fences_and_surrounding_prose() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": {"b": 2}} hope it helps') == {"a": {"b": 2}}


def test_extract_json_rejects_text_without_json() -> None:
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_loggable_messages_replace_images_with_size_and_hash() -> None:
    logged = loggable_messages([{"role": "user", "content": "x", "images": [PNG_B64]}])

    placeholder = logged[0]["images"][0]
    assert placeholder.startswith("<image png ")
    assert "sha256=" in placeholder
    assert PNG_B64 not in str(logged)


async def test_valid_answer_is_logged_once_with_schema_and_options(ctx: AgentContext) -> None:
    client = ScriptedLlmClient([rules_json()])

    result = await call_structured(
        ctx, _STEP, client, [{"role": "user", "content": "q"}], BusinessRules
    )

    assert [rule.rule_id for rule in result.rules] == ["BR-001", "BR-002", "BR-003"]
    calls = ctx.record["steps"][_STEP]["llm_calls"]
    assert len(calls) == 1
    assert calls[0]["valid"] is True
    assert calls[0]["raw_response"] == rules_json()
    assert calls[0]["messages"] == [{"role": "user", "content": "q"}]
    # Ollama gets the JSON schema (constrained decoding) and the context-window options.
    assert client.calls[0]["response_format"]["title"] == "BusinessRules"
    assert client.calls[0]["options"]["num_ctx"] > 2048


async def test_invalid_answer_is_repaired_and_both_attempts_logged(ctx: AgentContext) -> None:
    client = ScriptedLlmClient(['{"rules": [{"rule_id": "BR-001"}]}', rules_json()])

    result = await call_structured(
        ctx, _STEP, client, [{"role": "user", "content": "q"}], BusinessRules
    )

    assert len(result.rules) == 3
    calls = ctx.record["steps"][_STEP]["llm_calls"]
    assert [call["valid"] for call in calls] == [False, True]
    assert calls[0]["validation_errors"]
    # The repair attempt shows the model its own answer and the validation errors.
    repair = client.calls[1]["messages"]
    assert repair[-2]["role"] == "assistant"
    assert "not valid" in repair[-1]["content"]


async def test_two_invalid_answers_raise_after_logging(ctx: AgentContext) -> None:
    client = ScriptedLlmClient(["not json", "still not json"])

    with pytest.raises(AgentOutputValidationError):
        await call_structured(ctx, _STEP, client, [{"role": "user", "content": "q"}], BusinessRules)

    calls = ctx.record["steps"][_STEP]["llm_calls"]
    assert [call["parse_error"] is not None for call in calls] == [True, True]


async def test_google_provider_also_gets_the_json_schema(ctx: AgentContext) -> None:
    client = ScriptedLlmClient([rules_json()], provider="google")

    await call_structured(ctx, _STEP, client, [{"role": "user", "content": "q"}], BusinessRules)

    assert client.calls[0]["response_format"]["title"] == "BusinessRules"


class _FlakyClient(ScriptedLlmClient):
    """Fails with the given HTTP status `failures` times, then answers."""

    def __init__(self, failures: int, status: int, answer: str) -> None:
        super().__init__([answer])
        self._failures = failures
        self._status = status

    async def complete_chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        if self._failures > 0:
            self._failures -= 1
            request = httpx.Request("POST", "https://provider")
            response = httpx.Response(self._status, request=request)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                raise LlmClientError(f"google request failed: HTTP {self._status}") from error
        return await super().complete_chat(messages, **kwargs)


async def test_transient_503_is_retried_and_every_try_is_logged(
    ctx: AgentContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agents_retry_backoff_seconds", 0.0)
    client = _FlakyClient(failures=2, status=503, answer=rules_json())

    result = await call_structured(
        ctx, _STEP, client, [{"role": "user", "content": "q"}], BusinessRules
    )

    assert len(result.rules) == 3
    calls = ctx.record["steps"][_STEP]["llm_calls"]
    assert [c["transport_try"] for c in calls] == [1, 2, 3]
    assert ["503" in (c.get("error") or "") for c in calls] == [True, True, False]
    assert calls[-1]["valid"] is True


async def test_non_transient_error_is_not_retried(
    ctx: AgentContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agents_retry_backoff_seconds", 0.0)
    client = _FlakyClient(failures=1, status=400, answer=rules_json())

    with pytest.raises(LlmClientError):
        await call_structured(ctx, _STEP, client, [{"role": "user", "content": "q"}], BusinessRules)

    assert len(ctx.record["steps"][_STEP]["llm_calls"]) == 1


async def test_retries_stop_after_the_configured_count(
    ctx: AgentContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agents_retry_backoff_seconds", 0.0)
    monkeypatch.setattr(settings, "agents_transient_retries", 1)
    client = _FlakyClient(failures=5, status=503, answer=rules_json())

    with pytest.raises(LlmClientError):
        await call_structured(ctx, _STEP, client, [{"role": "user", "content": "q"}], BusinessRules)

    calls = ctx.record["steps"][_STEP]["llm_calls"]
    assert [c["transport_try"] for c in calls] == [1, 2]
    assert "retry_in_s" not in calls[-1]


def test_timeouts_are_not_transient_but_dropped_connections_are() -> None:
    request = httpx.Request("POST", "http://vision")
    timeout = LlmClientError("ollama request failed: ReadTimeout")
    timeout.__cause__ = httpx.ReadTimeout("slow", request=request)
    dropped = LlmClientError("ollama request failed: RemoteProtocolError")
    dropped.__cause__ = httpx.RemoteProtocolError("dropped", request=request)

    assert is_transient(timeout) is False
    assert is_transient(dropped) is True
