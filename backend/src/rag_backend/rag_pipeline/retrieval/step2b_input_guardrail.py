from __future__ import annotations

from dataclasses import dataclass

from rag_backend.config import settings
from rag_backend.guardrails import judge_client
from rag_backend.guardrails.schemas import BLOCKED_VERDICTS, GuardrailVerdict
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import NormalizedQuery


@dataclass
class InputGuardrailResult:
    query: NormalizedQuery
    verdict: GuardrailVerdict
    blocked: bool


async def check_input_guardrail(query: NormalizedQuery) -> InputGuardrailResult:
    """Screen the normalized user message for excessive length, prompt injection, or
    sensitive content before it reaches retrieval/embedding.

    A length-cap violation is checked first and produces a verdict without calling the
    judge LLM (cheap, deterministic, no wasted round-trip). Otherwise, when
    settings.guardrail_input_enabled is True, an LLM-as-judge call classifies the
    message; a judge failure or malformed output is fail-closed (blocked), consistent
    with rag_backend.guardrails.judge_client.judge().
    """
    if len(query.text) > settings.guardrail_max_input_chars:
        verdict = GuardrailVerdict(
            layer="input",
            verdict="unsafe",
            category="length_exceeded",
            reason=(
                f"Message length {len(query.text)} exceeds the "
                f"{settings.guardrail_max_input_chars} character limit."
            ),
        )
        return InputGuardrailResult(query=query, verdict=verdict, blocked=True)

    if not settings.guardrail_input_enabled:
        verdict = GuardrailVerdict(
            layer="input", verdict="safe", reason="Input guardrail disabled."
        )
        return InputGuardrailResult(query=query, verdict=verdict, blocked=False)

    verdict = await judge_client.judge(query.text, layer="input")
    return InputGuardrailResult(
        query=query, verdict=verdict, blocked=verdict.verdict in BLOCKED_VERDICTS
    )
