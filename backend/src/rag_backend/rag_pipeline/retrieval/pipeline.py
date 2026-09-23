from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from rag_backend.pipeline_logging import new_request_id, write_retrieval_log
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


def _log_step_end(
    step_name: str, started_at: float, record: dict[str, Any], output: dict[str, Any]
) -> None:
    """Log the step's result to the console AND record it in the per-request JSON file.

    Logging the actual output (not just the timing) at every step is what makes it
    possible to tell, from either the console or the log file, whether a given step
    behaved as expected — e.g. whether similarity search found anything, whether
    metadata filtering dropped chunks, whether the LLM call actually returned text.
    """
    elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
    logger.info("Retrieval step done: %s (%.1fms) -> %s", step_name, elapsed_ms, output)
    record["steps"][step_name] = {"duration_ms": elapsed_ms, "output": output}


async def run_retrieval(
    message: str, document_ids: list[str] | None = None
) -> AsyncIterator[bytes]:
    """Run the 10-step retrieval pipeline for one chat message.

    Streams the LLM's answer token-by-token, followed by a trailing citations
    payload (see step10_response). Every step logs its result (not just timing) to
    the console as it runs, so the pipeline's behavior is visible live; the full
    system prompt is logged right before the LLM call.

    The entire request — user message, every step's output and timing, the system
    prompt, the final answer, and citations (or the error, if one occurred) — is
    also written to a single JSON file under pipeline-logs/retrieval/ once the
    request finishes, so one exchange can be inspected without grepping logs.
    """
    record: dict[str, Any] = {
        "request_id": new_request_id(),
        "user_message": message,
        "document_ids_filter": document_ids,
        "steps": {},
    }
    answer_chunks: list[str] = []
    try:
        started = _log_step_start("1_get_input")
        raw_query = get_input(message, document_ids)
        _log_step_end(
            "1_get_input",
            started,
            record,
            {"message": raw_query.text, "document_ids": raw_query.document_ids},
        )

        started = _log_step_start("2_normalize_input")
        normalized = normalize_input(raw_query)
        record["normalized_query"] = normalized.text
        _log_step_end("2_normalize_input", started, record, {"normalized_text": normalized.text})

        started = _log_step_start("3_embedding_question")
        embedded_query = embed_question(normalized)
        _log_step_end(
            "3_embedding_question",
            started,
            record,
            {"embedding_dimension": len(embedded_query.embedding)},
        )

        started = _log_step_start("4_similarity_search")
        scored_chunks = await similarity_search(embedded_query)
        similarity_results = [
            {
                "document_id": item.chunk.document_id,
                "chunk_index": item.chunk.chunk_index,
                "similarity_score": item.similarity_score,
            }
            for item in scored_chunks
        ]
        record["similarity_search_results"] = similarity_results
        _log_step_end(
            "4_similarity_search",
            started,
            record,
            {"result_count": len(scored_chunks), "results": similarity_results},
        )

        started = _log_step_start("5_metadata_filter")
        filtered_chunks = apply_metadata_filter(scored_chunks, embedded_query)
        _log_step_end(
            "5_metadata_filter",
            started,
            record,
            {"input_count": len(scored_chunks), "output_count": len(filtered_chunks)},
        )

        started = _log_step_start("6_reranking")
        reranked_chunks = rerank(filtered_chunks)
        _log_step_end(
            "6_reranking",
            started,
            record,
            {"input_count": len(filtered_chunks), "output_count": len(reranked_chunks)},
        )

        started = _log_step_start("7_combine_context")
        context = await combine_context(reranked_chunks)
        citations = [citation.model_dump() for citation in context.citations]
        record["citations"] = citations
        _log_step_end(
            "7_combine_context",
            started,
            record,
            {"surviving_chunk_count": len(citations), "citations": citations},
        )

        started = _log_step_start("8_build_prompt")
        messages = build_prompt(normalized.text, context)
        record["messages_sent_to_llm"] = messages
        record["system_prompt"] = messages[0]["content"]
        _log_step_end("8_build_prompt", started, record, {"system_prompt": messages[0]["content"]})
        logger.info("System prompt for this request:\n%s", messages[0]["content"])

        logger.info("Retrieval step start: 9_call_llm_model (messages=%d)", len(messages))
        started = time.monotonic()
        async for token in call_llm_model(messages):
            answer_chunks.append(token)
            yield token.encode("utf-8")
        answer = "".join(answer_chunks)
        _log_step_end(
            "9_call_llm_model",
            started,
            record,
            {"answer_length_chars": len(answer), "answer": answer},
        )

        started = _log_step_start("10_response")
        citations_payload = build_citations_payload(context.citations)
        yield citations_payload
        _log_step_end(
            "10_response",
            started,
            record,
            {"citations_payload_bytes": len(citations_payload)},
        )
    except Exception as error:
        record["error"] = str(error)
        logger.exception("Retrieval pipeline failed for request %s", record["request_id"])
        raise
    finally:
        record["llm_response"] = "".join(answer_chunks)
        write_retrieval_log(record)
