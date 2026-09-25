from __future__ import annotations

import logging
from dataclasses import dataclass

from rag_backend.config import settings
from rag_backend.conversations.models import Turn
from rag_backend.llm_model import client as llm_model_client
from rag_backend.llm_model.client import LlmClientError
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import NormalizedQuery

logger = logging.getLogger(__name__)

CONTEXTUALIZE_SYSTEM_PROMPT = (
    "You rewrite a follow-up question from a conversation into a standalone question. "
    "Resolve every pronoun and reference (it, they, that, the second one, ...) using the "
    "conversation, and keep the user's wording otherwise. If the question is already "
    "standalone, return it unchanged. Do NOT answer the question. Reply with the "
    "standalone question only, on a single line, with no preamble."
)

# Long answers add little to resolving a reference and slow the rewrite down.
_ANSWER_EXCERPT_CHARS = 500
_QUOTES = "\"'`“”‘’"


@dataclass
class ContextualizedQuery:
    """The query retrieval and the cache run on, plus how it was obtained."""

    query: NormalizedQuery
    rewritten: bool
    error: str | None = None


def _format_history(history: list[Turn]) -> str:
    lines: list[str] = []
    for turn in history:
        answer = turn.answer
        if len(answer) > _ANSWER_EXCERPT_CHARS:
            answer = answer[:_ANSWER_EXCERPT_CHARS].rstrip() + " …"
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {answer}")
    return "\n".join(lines)


def build_contextualize_messages(question: str, history: list[Turn]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": CONTEXTUALIZE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Conversation:\n{_format_history(history)}\n\n"
                f"Follow-up question: {question}\n\n"
                "Standalone question:"
            ),
        },
    ]


def _clean_rewrite(text: str) -> str:
    """First non-empty line, without a "Standalone question:" echo or wrapping quotes."""
    line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    prefix = "standalone question:"
    if line.lower().startswith(prefix):
        line = line[len(prefix) :].strip()
    return line.strip(_QUOTES).strip()


async def contextualize(query: NormalizedQuery, history: list[Turn]) -> ContextualizedQuery:
    """Rewrite a follow-up into a standalone question using the conversation history.

    Runs before embedding and before the cache lookup, so "what about its limits?" is
    searched (and cached) as the full question it stands for. No history, or
    contextualize_enabled off -> the question passes through unchanged. An LLM failure
    or an empty rewrite also falls back to the original question: memory is a quality
    boost, never a reason to fail the request.

    Looks up llm_model_client.llm_client on every call so tests can monkeypatch it.
    """
    if not history or not settings.contextualize_enabled:
        return ContextualizedQuery(query=query, rewritten=False)
    messages = build_contextualize_messages(query.text, history)
    try:
        raw = await llm_model_client.llm_client.complete_chat(messages)
    except LlmClientError as error:
        logger.warning("Contextualize failed, using the question as typed: %s", error)
        return ContextualizedQuery(query=query, rewritten=False, error=str(error))
    standalone = _clean_rewrite(raw)
    if not standalone:
        return ContextualizedQuery(query=query, rewritten=False, error="empty rewrite")
    return ContextualizedQuery(
        query=NormalizedQuery(text=standalone, document_ids=query.document_ids),
        rewritten=standalone != query.text,
    )
