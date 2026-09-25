from __future__ import annotations

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
