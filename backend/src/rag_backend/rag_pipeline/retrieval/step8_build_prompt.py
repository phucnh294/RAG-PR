from __future__ import annotations

from rag_backend.rag_pipeline.retrieval.step7_combine_context import CombinedContext

SYSTEM_PROMPT_NO_CONTEXT = (
    "You are a helpful assistant. No relevant documents were found for this "
    "question. Tell the user you don't know based on the available documents."
)

SYSTEM_PROMPT_TEMPLATE = (
    "You are a helpful assistant that answers questions using ONLY the context below. "
    "Keep answers brief. If the context doesn't contain the answer, say you don't know.\n\n"
    "Context:\n{context}"
)


def build_prompt(query_text: str, context: CombinedContext) -> list[dict[str, str]]:
    """Assemble the system + user messages sent to the LLM from the combined context."""
    system_prompt = (
        SYSTEM_PROMPT_NO_CONTEXT
        if not context.citations
        else SYSTEM_PROMPT_TEMPLATE.format(context=context.context_text)
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query_text},
    ]
