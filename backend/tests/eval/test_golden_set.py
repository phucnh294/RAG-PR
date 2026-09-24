from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from rag_backend.eval.runner import run_golden_set
from rag_backend.eval.schemas import GoldenEntry
from rag_backend.guardrails import judge_client
from rag_backend.llm_model import client as llm_model_client
from rag_backend.llm_model.client import LlmClient
from tests.eval.fakes import ContextAwareLlmClient, HeuristicJudgeClient


@pytest.fixture(autouse=True)
def _real_ish_guardrail_doubles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override the conftest defaults (always-safe judge, scripted-token LLM) with
    doubles that actually react to input/context, so the golden set exercises
    meaningful behavior instead of trivially reporting 0% blocks everywhere.
    """
    monkeypatch.setattr(judge_client, "guardrail_judge_client", HeuristicJudgeClient())
    monkeypatch.setattr(llm_model_client, "llm_client", ContextAwareLlmClient())


async def test_golden_set_never_false_blocks_legitimate_traffic() -> None:
    report = await run_golden_set()

    by_category = {metrics.category: metrics for metrics in report.categories}

    assert by_category["real"].false_block_rate == 0.0
    assert by_category["expect"].false_block_rate == 0.0


async def test_golden_set_catches_attacks_and_measures_retrieval_quality() -> None:
    report = await run_golden_set()
    by_category = {metrics.category: metrics for metrics in report.categories}

    assert by_category["attack"].block_rate is not None
    assert by_category["attack"].block_rate > 0.0
    assert by_category["real"].recall_at_k is not None
    assert by_category["real"].mrr is not None
    assert by_category["expect"].refusal_rate is not None


async def test_golden_set_skips_a_failing_entry_instead_of_crashing_the_whole_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors the real incident this test guards against: a live Gemini eval run hit
    a 429 rate-limit mid-batch and the whole /eval/run request 500'd, losing every
    other entry's results. run_golden_set must skip a failing entry and keep going.
    """

    class FlakyLlmClient(LlmClient):
        def __init__(self) -> None:
            self._call_count = 0

        async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            self._call_count += 1
            if self._call_count == 1:
                raise RuntimeError("simulated provider rate limit (429)")
            yield "Based on the provided context, here is the answer."

    monkeypatch.setattr(llm_model_client, "llm_client", FlakyLlmClient())

    entries = [
        GoldenEntry(query="first real query", category="real", expected_document_filename=None),
        GoldenEntry(query="second real query", category="real", expected_document_filename=None),
    ]

    report = await run_golden_set(entries=entries)

    assert len(report.results) == 1
    assert report.results[0].query == "second real query"
