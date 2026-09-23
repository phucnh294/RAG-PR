from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from rag_backend.pipeline_logging import StepRecorder, new_request_id, write_retrieval_log
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

_PROCESS_NAME = "Retrieval"


async def run_retrieval(
    message: str, document_ids: list[str] | None = None
) -> AsyncIterator[bytes]:
    """Run the 10-step retrieval pipeline for one chat message.

    Streams the LLM's answer token-by-token, followed by a trailing citations
    payload (see step10_response). Every step logs its input AND its output as
    separate console lines ("Retrieval - {step} {timestamp} - input/output: {data}"),
    so the full request can be read start-to-end from the console alone. The same
    input/output/timestamps are written into a single JSON file under
    pipeline-logs/retrieval/ once the request finishes (see StepRecorder), so one
    exchange can also be inspected end-to-end without grepping logs.
    """
    record: dict[str, Any] = {
        "request_id": new_request_id(),
        "user_message": message,
        "document_ids_filter": document_ids,
        "steps": {},
    }
    steps = StepRecorder(logger, _PROCESS_NAME, record)
    answer_chunks: list[str] = []
    try:
        steps.log_input("1_get_input", {"message": message, "document_ids": document_ids})
        raw_query = get_input(message, document_ids)
        steps.log_output(
            "1_get_input", {"message": raw_query.text, "document_ids": raw_query.document_ids}
        )

        steps.log_input(
            "2_normalize_input",
            {"raw_text": raw_query.text, "document_ids": raw_query.document_ids},
        )
        normalized = normalize_input(raw_query)
        record["normalized_query"] = normalized.text
        steps.log_output("2_normalize_input", {"normalized_text": normalized.text})

        steps.log_input("3_embedding_question", {"normalized_text": normalized.text})
        embedded_query = await embed_question(normalized)
        steps.log_output(
            "3_embedding_question", {"embedding_dimension": len(embedded_query.embedding)}
        )

        steps.log_input(
            "4_similarity_search", {"embedding_dimension": len(embedded_query.embedding)}
        )
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
        steps.log_output(
            "4_similarity_search",
            {"result_count": len(scored_chunks), "results": similarity_results},
        )

        steps.log_input(
            "5_metadata_filter",
            {
                "scored_chunk_count": len(scored_chunks),
                "document_ids_filter": embedded_query.document_ids,
            },
        )
        filtered_chunks = apply_metadata_filter(scored_chunks, embedded_query)
        steps.log_output("5_metadata_filter", {"filtered_chunk_count": len(filtered_chunks)})

        steps.log_input("6_reranking", {"chunk_count": len(filtered_chunks)})
        reranked_chunks = rerank(filtered_chunks)
        steps.log_output("6_reranking", {"chunk_count": len(reranked_chunks)})

        steps.log_input("7_combine_context", {"chunk_count": len(reranked_chunks)})
        context = await combine_context(reranked_chunks)
        citations = [citation.model_dump() for citation in context.citations]
        record["citations"] = citations
        steps.log_output(
            "7_combine_context",
            {"surviving_chunk_count": len(citations), "citations": citations},
        )

        steps.log_input(
            "8_build_prompt",
            {"query_text": normalized.text, "citation_count": len(citations)},
        )
        messages = build_prompt(normalized.text, context)
        record["messages_sent_to_llm"] = messages
        record["system_prompt"] = messages[0]["content"]
        steps.log_output(
            "8_build_prompt", {"system_prompt": messages[0]["content"], "messages": messages}
        )

        steps.log_input("9_call_llm_model", {"messages": messages})
        async for token in call_llm_model(messages):
            answer_chunks.append(token)
            yield token.encode("utf-8")
        answer = "".join(answer_chunks)
        steps.log_output("9_call_llm_model", {"answer_length_chars": len(answer), "answer": answer})

        steps.log_input("10_response", {"citation_count": len(citations)})
        citations_payload = build_citations_payload(context.citations)
        yield citations_payload
        steps.log_output("10_response", {"citations_payload_bytes": len(citations_payload)})
    except Exception as error:
        record["error"] = str(error)
        logger.exception("Retrieval pipeline failed for request %s", record["request_id"])
        raise
    finally:
        record["llm_response"] = "".join(answer_chunks)
        write_retrieval_log(record)
