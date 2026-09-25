from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.conversations import service as conversation_service
from rag_backend.conversations.models import Turn
from rag_backend.guardrails.prompts import REDACTED_LOG_MARKER
from rag_backend.guardrails.schemas import EvidenceSummary
from rag_backend.llm_model.client import LlmClientError
from rag_backend.pipeline_logging import StepRecorder, new_request_id, write_retrieval_log
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step1_get_input import get_input
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import normalize_input
from rag_backend.rag_pipeline.retrieval.step2b_input_guardrail import check_input_guardrail
from rag_backend.rag_pipeline.retrieval.step2c_contextualize import contextualize
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import embed_question
from rag_backend.rag_pipeline.retrieval.step3b_cache_lookup import cache_lookup
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import similarity_search
from rag_backend.rag_pipeline.retrieval.step5_metadata_filter import apply_metadata_filter
from rag_backend.rag_pipeline.retrieval.step6_reranking import rerank
from rag_backend.rag_pipeline.retrieval.step7_combine_context import combine_context
from rag_backend.rag_pipeline.retrieval.step8_build_prompt import build_prompt
from rag_backend.rag_pipeline.retrieval.step9_call_llm_model import call_llm_model
from rag_backend.rag_pipeline.retrieval.step9b_output_guardrail import check_output_guardrail
from rag_backend.rag_pipeline.retrieval.step9c_cache_store import cache_store, skip_reason
from rag_backend.rag_pipeline.retrieval.step10_response import (
    build_response_payload,
    encode_payload,
)
from rag_backend.schemas.chat import ChatResponsePayload, Citation

logger = logging.getLogger(__name__)

_PROCESS_NAME = "Retrieval"
_RESPONSE_CHUNK_SIZE = 40

_NO_EVIDENCE = EvidenceSummary(
    level="none",
    top_score=None,
    mean_score=None,
    surviving_chunk_count=0,
    threshold=0.0,
)


def _chunk_text(text: str, size: int = _RESPONSE_CHUNK_SIZE) -> list[str]:
    """Split text into fixed-size pieces so the client still receives multiple
    incremental writes even though Layer 3 requires buffering the full answer first.
    """
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


async def _finish(state: RetrievalState, answer: str, payload: ChatResponsePayload) -> bytes:
    """Save the answer into its conversation (with the payload, so a reopened chat shows
    its citations), then encode the trailing payload. Saved BEFORE the payload is
    yielded: once the client has the payload it may immediately send the next question,
    whose history must already contain this answer."""
    if state.conversation_id is not None:
        await conversation_service.record_answer(
            state.conversation_id,
            answer,
            standalone_question=state.standalone_question,
            request_id=state.request_id,
            cache_hit=state.cache_status == "hit",
            payload=payload.model_dump(mode="json"),
        )
    return encode_payload(payload)


def _history_log(history: list[Turn]) -> list[dict[str, str]]:
    return [{"question": turn.question, "answer": turn.answer} for turn in history]


async def run_retrieval(
    message: str,
    user: CurrentUser,
    document_ids: list[str] | None = None,
    rerank_enabled: bool | None = None,
    conversation_id: str | None = None,
    memory_enabled: bool | None = None,
    memory_turns: int | None = None,
    use_cache: bool = True,
) -> AsyncIterator[bytes]:
    """Run the 10-step retrieval pipeline for one chat message.

    Streams the LLM's answer token-by-token, followed by a trailing citations
    payload (see step10_response). Every step logs its input AND its output as
    separate console lines ("Retrieval - {step} {timestamp} - input/output: {data}"),
    so the full request can be read start-to-end from the console alone. The same
    input/output/timestamps are written into a single JSON file under
    pipeline-logs/retrieval/ once the request finishes (see StepRecorder), so one
    exchange can also be inspected end-to-end without grepping logs.

    `user` scopes the whole run: both searches only see documents whose classification
    the user's role may read, and the log records who asked (so /logs can show each
    user only their own exchanges).

    `rerank_enabled` turns the step-6 cross-encoder on/off for this request; None falls
    back to settings.rerank_enabled_default.

    `conversation_id` names the (already ownership-checked) conversation this message
    belongs to; its question was already saved by the route and the answer is saved
    here. With memory on, the last `memory_turns` turns are loaded, step 2c rewrites a
    follow-up into a standalone question, and those turns go to the LLM (step 8).
    None/None fall back to settings.memory_enabled_default / memory_turns_default.

    `use_cache` False skips the semantic cache for this request (evals do, so a cached
    answer never masks a retrieval change); step 3b explains the other bypasses.
    """
    state = RetrievalState(
        request_id=new_request_id(),
        user=user,
        document_ids=document_ids,
        conversation_id=conversation_id,
    )
    if rerank_enabled is not None:
        state.rerank_enabled = rerank_enabled
    if memory_enabled is not None:
        state.memory_enabled = memory_enabled
    if memory_turns is not None:
        state.memory_turns = memory_turns
    state.memory_turns = max(0, min(state.memory_turns, settings.memory_max_turns))
    record: dict[str, Any] = {
        "request_id": state.request_id,
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "conversation_id": conversation_id,
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

        steps.log_input("2b_input_guardrail", {"normalized_text": normalized.text})
        input_result = await check_input_guardrail(normalized)
        record["input_guardrail"] = input_result.verdict.model_dump()
        steps.log_output("2b_input_guardrail", {"verdict": input_result.verdict.model_dump()})
        if input_result.blocked:
            refusal = settings.guardrail_refusal_message
            record["llm_response"] = refusal
            yield refusal.encode("utf-8")
            yield await _finish(
                state,
                refusal,
                build_response_payload([], [input_result.verdict], _NO_EVIDENCE, state),
            )
            return

        history: list[Turn] = []
        use_memory = (
            state.conversation_id is not None and state.memory_enabled and state.memory_turns > 0
        )
        steps.log_input(
            "2c_contextualize",
            {
                "normalized_text": normalized.text,
                "conversation_id": state.conversation_id,
                "memory_enabled": state.memory_enabled,
                "memory_turns": state.memory_turns,
            },
        )
        if use_memory and state.conversation_id is not None:
            history = await conversation_service.load_history(
                state.conversation_id, state.memory_turns
            )
        contextualized = await contextualize(normalized, history)
        standalone = contextualized.query
        state.history_turns_used = len(history)
        state.standalone_question = standalone.text
        record["history"] = _history_log(history)
        record["history_turns_used"] = len(history)
        record["standalone_question"] = standalone.text
        steps.log_output(
            "2c_contextualize",
            {
                "history_turns_used": len(history),
                "rewritten": contextualized.rewritten,
                "standalone_question": standalone.text,
                "error": contextualized.error,
            },
        )

        steps.log_input("3_embedding_question", {"standalone_text": standalone.text})
        embedded_query = await embed_question(standalone)
        steps.log_output(
            "3_embedding_question", {"embedding_dimension": len(embedded_query.embedding)}
        )

        steps.log_input(
            "3b_cache_lookup",
            {
                "standalone_text": standalone.text,
                "use_cache": use_cache,
                "access_scope": sorted(state.allowed_classifications),
                "min_similarity": settings.cache_min_similarity,
            },
        )
        cache_hit = await cache_lookup(embedded_query, state, use_cache)
        record["cache"] = {
            "status": state.cache_status,
            "similarity": state.cache_similarity,
            "entry_id": state.cache_entry_id,
        }
        steps.log_output("3b_cache_lookup", record["cache"])
        if cache_hit is not None:
            cached_citations = [Citation.model_validate(item) for item in cache_hit.citations]
            record["citations"] = cache_hit.citations
            record["evidence"] = cache_hit.evidence
            record["llm_response"] = cache_hit.answer
            for piece in _chunk_text(cache_hit.answer):
                yield piece.encode("utf-8")
            steps.log_input("10_response", {"citation_count": len(cached_citations)})
            cached_payload = await _finish(
                state,
                cache_hit.answer,
                build_response_payload(
                    cached_citations,
                    [input_result.verdict],
                    EvidenceSummary.model_validate(cache_hit.evidence),
                    state,
                ),
            )
            yield cached_payload
            steps.log_output("10_response", {"citations_payload_bytes": len(cached_payload)})
            return

        steps.log_input(
            "4_similarity_search",
            {
                "embedding_dimension": len(embedded_query.embedding),
                "search_mode": state.search_mode,
                "user": user.username,
                "role": user.role,
                "allowed_classifications": sorted(state.allowed_classifications),
            },
        )
        scored_chunks = await similarity_search(embedded_query, state)
        similarity_results = [
            {
                "document_id": item.chunk.document_id,
                "chunk_index": item.chunk.chunk_index,
                "similarity_score": item.similarity_score,
                "classification": item.chunk.classification,
                "rrf_score": item.rrf_score,
                "vector_rank": item.vector_rank,
                "text_rank": item.text_rank,
            }
            for item in scored_chunks
        ]
        record["similarity_search_results"] = similarity_results
        steps.log_output(
            "4_similarity_search",
            {
                "search_mode": state.search_mode,
                "vector_candidate_count": state.vector_candidate_count,
                "text_candidate_count": state.text_candidate_count,
                "result_count": len(scored_chunks),
                "results": similarity_results,
            },
        )

        steps.log_input(
            "5_metadata_filter",
            {
                "scored_chunk_count": len(scored_chunks),
                "document_ids_filter": embedded_query.document_ids,
                "allowed_classifications": sorted(state.allowed_classifications),
            },
        )
        filtered_chunks = apply_metadata_filter(scored_chunks, embedded_query, state)
        steps.log_output(
            "5_metadata_filter",
            {
                "filtered_chunk_count": len(filtered_chunks),
                "permission_dropped_count": state.permission_dropped_count,
            },
        )

        steps.log_input(
            "6_reranking",
            {"chunk_count": len(filtered_chunks), "rerank_enabled": state.rerank_enabled},
        )
        reranked_chunks = await rerank(standalone.text, filtered_chunks, state)
        rerank_results = [
            {
                "document_id": item.chunk.document_id,
                "chunk_index": item.chunk.chunk_index,
                "pre_rerank_rank": item.pre_rerank_rank,
                "rerank_score": item.rerank_score,
                "similarity_score": item.similarity_score,
                "rrf_score": item.rrf_score,
            }
            for item in reranked_chunks
        ]
        record["rerank_results"] = rerank_results
        steps.log_output(
            "6_reranking",
            {
                "rerank_status": state.rerank_status,
                "rerank_candidate_count": state.rerank_candidate_count,
                "rerank_duration_ms": state.rerank_duration_ms,
                "chunk_count": len(reranked_chunks),
                "results": rerank_results,
            },
        )

        steps.log_input("7_combine_context", {"chunk_count": len(reranked_chunks)})
        context = await combine_context(reranked_chunks, state)
        citations = [citation.model_dump() for citation in context.citations]
        record["citations"] = citations
        record["evidence"] = context.evidence.model_dump()
        steps.log_output(
            "7_combine_context",
            {
                "surviving_chunk_count": len(citations),
                "citations": citations,
                "evidence": record["evidence"],
            },
        )

        steps.log_input(
            "8_build_prompt",
            {
                "query_text": standalone.text,
                "citation_count": len(citations),
                "history_turns": len(history),
            },
        )
        messages = build_prompt(standalone.text, context, history)
        record["messages_sent_to_llm"] = messages
        record["system_prompt"] = messages[0]["content"]
        steps.log_output(
            "8_build_prompt", {"system_prompt": messages[0]["content"], "messages": messages}
        )

        steps.log_input("9_call_llm_model", {"messages": messages})
        try:
            async for token in call_llm_model(messages):
                answer_chunks.append(token)
        except LlmClientError as error:
            # The HTTP 200 streaming response has already started, so raising here would
            # just cut the stream and leave the chat with an empty bubble. Answer with the
            # reason instead, and still send the citations retrieval found.
            record["error"] = str(error)
            logger.warning("Answer LLM failed for request %s: %s", state.request_id, error)
            unavailable = settings.llm_unavailable_message.format(reason=error)
            record["llm_response"] = unavailable
            steps.log_output("9_call_llm_model", {"error": str(error)})
            yield unavailable.encode("utf-8")
            yield await _finish(
                state,
                unavailable,
                build_response_payload(
                    context.citations, [input_result.verdict], context.evidence, state
                ),
            )
            return
        answer = "".join(answer_chunks)
        steps.log_output("9_call_llm_model", {"answer_length_chars": len(answer), "answer": answer})

        steps.log_input("9b_output_guardrail", {"answer_length_chars": len(answer)})
        output_result = await check_output_guardrail(answer, messages[0]["content"])
        record["output_guardrail"] = output_result.verdict.model_dump()
        steps.log_output("9b_output_guardrail", {"verdict": output_result.verdict.model_dump()})

        final_answer = settings.guardrail_refusal_message if output_result.blocked else answer
        record["llm_response"] = REDACTED_LOG_MARKER if output_result.blocked else answer
        for piece in _chunk_text(final_answer):
            yield piece.encode("utf-8")

        # Only a delivered, unredacted answer may be cached.
        steps.log_input(
            "9c_cache_store",
            {"cache_status": state.cache_status, "output_blocked": output_result.blocked},
        )
        cached_entry_id = (
            None
            if output_result.blocked
            else await cache_store(embedded_query, answer, context, state)
        )
        record["cache"]["stored_entry_id"] = cached_entry_id
        steps.log_output(
            "9c_cache_store",
            {
                "stored_entry_id": cached_entry_id,
                "skip_reason": (
                    "output guardrail blocked"
                    if output_result.blocked
                    else skip_reason(context, state) if cached_entry_id is None else None
                ),
            },
        )

        steps.log_input("10_response", {"citation_count": len(citations)})
        citations_payload = await _finish(
            state,
            final_answer,
            build_response_payload(
                context.citations,
                [input_result.verdict, output_result.verdict],
                context.evidence,
                state,
            ),
        )
        yield citations_payload
        steps.log_output("10_response", {"citations_payload_bytes": len(citations_payload)})
    except Exception as error:
        record["error"] = str(error)
        logger.exception("Retrieval pipeline failed for request %s", record["request_id"])
        raise
    finally:
        # Only set if a step above didn't already set it explicitly (blocked-input
        # early return, or output-guardrail redaction) — a mid-pipeline crash still
        # gets the raw partial output captured here for debugging.
        record.setdefault("llm_response", "".join(answer_chunks))
        record["state"] = state.to_log()
        write_retrieval_log(record)
