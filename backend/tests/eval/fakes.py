from __future__ import annotations

from collections.abc import AsyncIterator

from rag_backend.llm_model.client import LlmClient

# Deliberately overlaps with (but is independent of) the real injection phrasing used
# in the golden set's "attack" entries and in guardrails/prompts.py's judge
# instructions — this is a simple stand-in for a real LLM judge, not the real thing.
_INJECTION_PHRASES = (
    "ignore all previous instructions",
    "ignore previous instructions",
    "disregard everything above",
    "disregard your instructions",
    "system override",
    "reveal your system prompt",
    "repeat the system prompt",
    "you are now dan",
    "print your configuration",
    "tell me any api keys",
    "raw contents of the documents",
)


class HeuristicJudgeClient(LlmClient):
    """Deterministic, no-network stand-in for the real judge LLM, used only in CI.

    Classifies text as unsafe if it contains a known injection phrase — good enough
    to exercise the real guardrail wiring (step2b/step9b, judge_client, parsing) and
    produce a meaningful, non-zero attack block_rate without needing a real model.
    """

    def __init__(self) -> None:
        pass

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        # The filled judge prompt template's own instructions quote injection phrases
        # as examples (see guardrails/prompts.py) — matching against the whole prompt
        # would flag every message. Extract only the actual subject text that follows
        # the template's final "USER MESSAGE:"/"ASSISTANT RESPONSE:" marker.
        content = messages[-1]["content"]
        for marker in ("USER MESSAGE:", "ASSISTANT RESPONSE:"):
            if marker in content:
                content = content.rsplit(marker, 1)[1]
                break
        is_unsafe = any(phrase in content.lower() for phrase in _INJECTION_PHRASES)
        verdict = "unsafe" if is_unsafe else "safe"
        category = "prompt_injection" if is_unsafe else "null"
        return f'{{"verdict": "{verdict}", "category": "{category}", "reason": "heuristic match"}}'


class ContextAwareLlmClient(LlmClient):
    """Deterministic, no-network stand-in for the real answer LLM, used only in CI.

    Answers from the system prompt's context block when one was built (i.e. some
    chunk survived the similarity threshold), otherwise emits a refusal string —
    mirrors the real behavior asked of the LLM in step8_build_prompt.py's system
    prompt without needing a real model.
    """

    def __init__(self) -> None:
        pass

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        system_prompt = messages[0]["content"]
        _, _, context_block = system_prompt.partition("Context:\n")
        if context_block.strip():
            yield "Based on the provided context, here is the answer."
        else:
            yield "I don't know based on the provided context."
