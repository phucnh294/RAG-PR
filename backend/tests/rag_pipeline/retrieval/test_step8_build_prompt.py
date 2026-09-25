from __future__ import annotations

from rag_backend.conversations.models import Turn
from rag_backend.guardrails.schemas import EvidenceSummary
from rag_backend.rag_pipeline.retrieval.step7_combine_context import CombinedContext
from rag_backend.rag_pipeline.retrieval.step8_build_prompt import build_prompt
from rag_backend.schemas.chat import Citation

_NO_EVIDENCE = EvidenceSummary(
    level="none", top_score=None, mean_score=None, surviving_chunk_count=0, threshold=0.7
)


def test_build_prompt_includes_context_when_citations_exist() -> None:
    context = CombinedContext(
        citations=[
            Citation(document_id="doc-1", filename="f.md", excerpt="hello", similarity_score=0.9)
        ],
        context_text="[1] (f.md) hello",
        evidence=_NO_EVIDENCE,
    )

    messages = build_prompt("what is hello?", context)

    assert messages[1] == {"role": "user", "content": "what is hello?"}
    assert "[1] (f.md) hello" in messages[0]["content"]


def test_build_prompt_asks_the_llm_to_say_it_does_not_know_when_no_citations() -> None:
    context = CombinedContext(citations=[], context_text="", evidence=_NO_EVIDENCE)

    messages = build_prompt("anything?", context)

    assert "say you" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "anything?"}


def test_build_prompt_puts_history_turns_between_system_and_question() -> None:
    context = CombinedContext(citations=[], context_text="", evidence=_NO_EVIDENCE)
    history = [
        Turn(question="first?", answer="one."),
        Turn(question="second?", answer="two."),
    ]

    messages = build_prompt("third?", context, history)

    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == "first?"
    assert messages[4]["content"] == "two."
    assert messages[-1] == {"role": "user", "content": "third?"}
