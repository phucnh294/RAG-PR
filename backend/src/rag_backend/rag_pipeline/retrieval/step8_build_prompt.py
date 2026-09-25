from __future__ import annotations

from rag_backend.conversations.models import Turn
from rag_backend.rag_pipeline.retrieval.step7_combine_context import CombinedContext

SYSTEM_PROMPT_TEMPLATE = (
    "You are a helpful assistant answering questions using only the context "
    "provided below. If the context does not contain the answer, say you "
    "don't know instead of guessing.\n\n"
    "Context:\n{context}"
)


def build_prompt(
    query_text: str, context: CombinedContext, history: list[Turn] | None = None
) -> list[dict[str, str]]:
    """Assemble the messages sent to the LLM: the system prompt with the combined
    context, the conversation's recent turns (conversation memory, oldest first) as
    alternating user/assistant messages, then the question.

    Always calls the LLM, even with no surviving context — the system prompt asks it
    to say it doesn't know rather than guess (see SYSTEM_PROMPT_TEMPLATE).
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context.context_text)
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history or []:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    messages.append({"role": "user", "content": query_text})
    return messages
