from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

from rag_backend.rag_pipeline.retrieval.step1_get_input import get_input
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import normalize_input
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import embed_question
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import similarity_search
from rag_backend.rag_pipeline.retrieval.step5_metadata_filter import apply_metadata_filter
from rag_backend.rag_pipeline.retrieval.step6_reranking import rerank
from rag_backend.rag_pipeline.retrieval.step7_combine_context import combine_context
from rag_backend.rag_pipeline.retrieval.step8_build_prompt import build_prompt
from rag_backend.rag_pipeline.retrieval.step9_call_llm_model import call_llm_model
from rag_backend.rag_pipeline.retrieval.step10_response import build_citations_payload

logger = logging.getLogger(__name__)


def _log_step_start(step_name: str) -> float:
    logger.info("Retrieval step start: %s", step_name)
    return time.monotonic()


def _log_step_end(step_name: str, started_at: float) -> None:
    elapsed_ms = (time.monotonic() - started_at) * 1000
    logger.info("Retrieval step done: %s (%.1fms)", step_name, elapsed_ms)


async def run_retrieval(
    message: str, document_ids: list[str] | None = None
) -> AsyncIterator[bytes]:
    """Run the 10-step retrieval pipeline for one chat message.

    Streams the LLM's answer token-by-token, followed by a trailing citations
    payload (see step10_response). Every step logs before and after it runs; the
    full system prompt is logged right before the LLM call.
    """
    started = _log_step_start("1_get_input")
    raw_query = get_input(message, document_ids)
    _log_step_end("1_get_input", started)

    started = _log_step_start("2_normalize_input")
    normalized = normalize_input(raw_query)
    _log_step_end("2_normalize_input", started)

    started = _log_step_start("3_embedding_question")
    embedded_query = embed_question(normalized)
    _log_step_end("3_embedding_question", started)

    started = _log_step_start("4_similarity_search")
    scored_chunks = await similarity_search(embedded_query)
    _log_step_end("4_similarity_search", started)

    started = _log_step_start("5_metadata_filter")
    filtered_chunks = apply_metadata_filter(scored_chunks, embedded_query)
    _log_step_end("5_metadata_filter", started)

    started = _log_step_start("6_reranking")
    reranked_chunks = rerank(filtered_chunks)
    _log_step_end("6_reranking", started)

    started = _log_step_start("7_combine_context")
    context = await combine_context(reranked_chunks)
    _log_step_end("7_combine_context", started)

    started = _log_step_start("8_build_prompt")
    messages = build_prompt(normalized.text, context)
    _log_step_end("8_build_prompt", started)
    logger.info("System prompt for this request:\n%s", messages[0]["content"])

    logger.info("Retrieval step start: 9_call_llm_model (messages=%d)", len(messages))
    started = time.monotonic()
    async for token in call_llm_model(messages):
        yield token.encode("utf-8")
    _log_step_end("9_call_llm_model", started)

    started = _log_step_start("10_response")
    yield build_citations_payload(context.citations)
    _log_step_end("10_response", started)
