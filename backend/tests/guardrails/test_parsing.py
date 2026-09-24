from __future__ import annotations

from rag_backend.guardrails.parsing import parse_judge_verdict


def test_parses_clean_json() -> None:
    verdict = parse_judge_verdict(
        '{"verdict": "safe", "category": null, "reason": "looks fine"}', "input"
    )

    assert verdict.verdict == "safe"
    assert verdict.category is None
    assert verdict.reason == "looks fine"
    assert verdict.layer == "input"


def test_parses_json_wrapped_in_prose_and_code_fence() -> None:
    raw = 'Sure, here is the classification:\n```json\n{"verdict": "unsafe", "category": "injection", "reason": "prompt injection detected"}\n```'

    verdict = parse_judge_verdict(raw, "output")

    assert verdict.verdict == "unsafe"
    assert verdict.category == "injection"


def test_missing_verdict_key_is_judge_error() -> None:
    verdict = parse_judge_verdict('{"category": "x", "reason": "y"}', "input")

    assert verdict.verdict == "judge_error"


def test_invalid_verdict_value_is_judge_error() -> None:
    verdict = parse_judge_verdict('{"verdict": "maybe", "reason": "unsure"}', "input")

    assert verdict.verdict == "judge_error"


def test_empty_string_is_judge_error() -> None:
    verdict = parse_judge_verdict("", "output")

    assert verdict.verdict == "judge_error"


def test_non_json_text_is_judge_error() -> None:
    verdict = parse_judge_verdict("I cannot classify this.", "output")

    assert verdict.verdict == "judge_error"
