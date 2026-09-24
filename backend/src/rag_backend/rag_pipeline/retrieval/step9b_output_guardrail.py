from __future__ import annotations

from dataclasses import dataclass

from rag_backend.config import settings
from rag_backend.guardrails import judge_client
from rag_backend.guardrails.schemas import BLOCKED_VERDICTS, GuardrailVerdict


@dataclass
class OutputGuardrailResult:
    answer_text: str
    verdict: GuardrailVerdict
    blocked: bool


async def check_output_guardrail(answer_text: str, system_prompt: str) -> OutputGuardrailResult:
    """Screen the LLM's fully buffered answer for leaked system-prompt content, leaked
    secrets/config, or echoed injected instructions before it reaches the client.

    A judge failure or malformed output is fail-closed (blocked): a missed leak is
    worse than an unnecessary refusal. No-ops to a "safe" verdict when
    settings.guardrail_output_enabled is False.
    """
    if not settings.guardrail_output_enabled:
        verdict = GuardrailVerdict(
            layer="output", verdict="safe", reason="Output guardrail disabled."
        )
        return OutputGuardrailResult(answer_text=answer_text, verdict=verdict, blocked=False)

    verdict = await judge_client.judge(answer_text, layer="output", system_prompt=system_prompt)
    return OutputGuardrailResult(
        answer_text=answer_text, verdict=verdict, blocked=verdict.verdict in BLOCKED_VERDICTS
    )
