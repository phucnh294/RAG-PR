from __future__ import annotations

import json
import re
from typing import Literal

from rag_backend.guardrails.schemas import GuardrailVerdict

_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
_VALID_VERDICTS = {"safe", "unsafe"}


def parse_judge_verdict(raw_text: str, layer: Literal["input", "output"]) -> GuardrailVerdict:
    """Parse a judge LLM's raw text reply into a GuardrailVerdict.

    Tries json.loads on the full text first, then falls back to extracting the first
    {...} block (models routinely wrap JSON in prose or code fences). Any failure —
    no JSON found, missing "verdict" key, or a verdict outside {"safe", "unsafe"} —
    returns verdict="judge_error" instead of raising, so callers apply one fail-closed
    policy uniformly regardless of why the judge output couldn't be trusted.
    """
    parsed = _try_parse(raw_text)
    if parsed is None or parsed.get("verdict") not in _VALID_VERDICTS:
        return GuardrailVerdict(
            layer=layer,
            verdict="judge_error",
            reason="Judge response could not be parsed into a valid verdict.",
            category=None,
        )

    return GuardrailVerdict(
        layer=layer,
        verdict=parsed["verdict"],
        reason=str(parsed.get("reason", ""))[:200],
        category=parsed.get("category") or None,
    )


def _try_parse(raw_text: str) -> dict | None:
    for candidate in (raw_text, _extract_json_block(raw_text)):
        if candidate is None:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _extract_json_block(raw_text: str) -> str | None:
    match = _JSON_OBJECT_PATTERN.search(raw_text)
    return match.group(0) if match else None
