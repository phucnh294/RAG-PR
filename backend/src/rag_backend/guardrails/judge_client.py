from __future__ import annotations

from typing import Literal

from rag_backend.config import settings
from rag_backend.exceptions import GuardrailJudgeError
from rag_backend.guardrails.parsing import parse_judge_verdict
from rag_backend.guardrails.prompts import (
    INPUT_GUARDRAIL_PROMPT_TEMPLATE,
    OUTPUT_GUARDRAIL_PROMPT_TEMPLATE,
)
from rag_backend.guardrails.schemas import GuardrailVerdict
from rag_backend.llm_model.client import LlmClient, LlmClientError

guardrail_judge_client = LlmClient(
    base_url=settings.guardrail_judge_base_url or settings.llm_base_url,
    model_name=settings.guardrail_judge_model_name or settings.llm_model_name,
    provider=settings.guardrail_judge_provider or settings.llm_provider,
    request_timeout_seconds=settings.guardrail_judge_timeout_seconds,
)

_PROMPT_TEMPLATES = {
    "input": INPUT_GUARDRAIL_PROMPT_TEMPLATE,
    "output": OUTPUT_GUARDRAIL_PROMPT_TEMPLATE,
}


async def judge(
    subject_text: str,
    layer: Literal["input", "output"],
    system_prompt: str | None = None,
) -> GuardrailVerdict:
    """Run one non-streaming judge call and return a parsed, never-raising verdict.

    Fail-closed: any judge LLM failure (network/timeout, bad response) or unparsable
    judge output returns verdict="judge_error" rather than raising — infra failures
    and malformed-output failures are indistinguishable to callers by design, both
    are treated as blocked, since a missed leak/injection is worse than a false refusal.
    """
    prompt = _PROMPT_TEMPLATES[layer].format(
        subject_text=subject_text, system_prompt=system_prompt or ""
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        raw_response = await guardrail_judge_client.complete_chat(messages)
    except (LlmClientError, GuardrailJudgeError) as error:
        return GuardrailVerdict(
            layer=layer,
            verdict="judge_error",
            reason=f"Guardrail judge call failed: {error}",
            category=None,
        )

    return parse_judge_verdict(raw_response, layer)
