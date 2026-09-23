from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step7_combine_context import CombinedContext

SYSTEM_PROMPT_TEMPLATE = (
    "You are a helpful assistant answering questions using only the context "
    "provided below. If the context does not contain the answer, say you "
    "don't know instead of guessing.\n\n"
    "Context:\n{context}"
)


def build_prompt(query_text: str, context: CombinedContext) -> list[dict[str, str]]:
    """Assemble the system + user messages sent to the LLM from the combined context.

    Always calls the LLM, even with no surviving context — the system prompt asks it
    to say it doesn't know rather than guess (see SYSTEM_PROMPT_TEMPLATE).
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context.context_text)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query_text},
    ]
