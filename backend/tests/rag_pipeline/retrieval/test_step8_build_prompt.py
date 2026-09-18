from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step7_combine_context import CombinedContext
from rag_backend.rag_pipeline.retrieval.step8_build_prompt import build_prompt
from rag_backend.schemas.chat import Citation


def test_build_prompt_includes_context_when_citations_exist() -> None:
    context = CombinedContext(
        citations=[
            Citation(document_id="doc-1", filename="f.md", excerpt="hello", similarity_score=0.9)
        ],
        context_text="[1] (f.md) hello",
    )

    messages = build_prompt("what is hello?", context)

    assert messages[1] == {"role": "user", "content": "what is hello?"}
    assert "[1] (f.md) hello" in messages[0]["content"]


def test_build_prompt_uses_no_context_prompt_when_no_citations() -> None:
    context = CombinedContext(citations=[], context_text="")

    messages = build_prompt("anything?", context)

    assert "No relevant documents were found" in messages[0]["content"]
