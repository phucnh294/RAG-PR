from __future__ import annotations

import logging
import time
from typing import Any

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.exceptions import RagBackendError
from rag_backend.pipeline_logging import write_indexing_log
from rag_backend.rag_pipeline.indexing.step1_load_input import load_input
from rag_backend.rag_pipeline.indexing.step2_document_parsing import parse_document
from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import chunk_text
from rag_backend.rag_pipeline.indexing.step4_preprocessing import preprocess_chunks
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import extract_metadata
from rag_backend.rag_pipeline.indexing.step6_embedding import embed_chunks
from rag_backend.rag_pipeline.indexing.step7_store_documents import store_document
from rag_backend.rag_pipeline.indexing.step8_store_chunks import store_chunks

logger = logging.getLogger(__name__)

_MAX_EXCERPTS_FOR_CITATIONS = 2


def _log_step_start(step_name: str) -> float:
    logger.info("Indexing step start: %s", step_name)
    return time.monotonic()


def _log_step_end(step_name: str, started_at: float, timings_ms: dict[str, float]) -> None:
    elapsed_ms = (time.monotonic() - started_at) * 1000
    logger.info("Indexing step done: %s (%.1fms)", step_name, elapsed_ms)
    timings_ms[step_name] = round(elapsed_ms, 1)


async def run_indexing(document_id: str, filename: str, mime_type: str) -> None:
    """Run all 8 indexing steps in order for one already-uploaded document.

    On any domain error (unsupported/unparseable file, etc.), marks the document
    failed with the error message rather than leaving it stuck in "pending" or
    partially indexed (steps 7/8 never run on failure).

    The full run — filename, mime type, per-step timings, resulting chunk count,
    and the error if one occurred — is also written to a JSON file under
    pipeline-logs/indexing/, mirroring the retrieval pipeline's per-request logs.
    """
    timings_ms: dict[str, float] = {}
    record: dict[str, Any] = {
        "document_id": document_id,
        "filename": filename,
        "mime_type": mime_type,
    }
    embedded_chunks: list[Any] = []
    try:
        started = _log_step_start("1_load_input")
        loaded_file = load_input(document_id, filename, mime_type)
        _log_step_end("1_load_input", started, timings_ms)

        started = _log_step_start("2_document_parsing")
        parsed = parse_document(loaded_file)
        _log_step_end("2_document_parsing", started, timings_ms)

        started = _log_step_start("3_chunking_strategy")
        chunks = chunk_text(parsed, settings.chunk_size_words, settings.chunk_overlap_words)
        _log_step_end("3_chunking_strategy", started, timings_ms)

        started = _log_step_start("4_preprocessing")
        chunks = preprocess_chunks(chunks)
        _log_step_end("4_preprocessing", started, timings_ms)

        started = _log_step_start("5_extract_metadata")
        chunks_with_metadata = extract_metadata(chunks)
        _log_step_end("5_extract_metadata", started, timings_ms)

        started = _log_step_start("6_embedding")
        embedded_chunks = embed_chunks(chunks_with_metadata)
        _log_step_end("6_embedding", started, timings_ms)

        excerpts = [
            item.chunk.content for item in chunks_with_metadata[:_MAX_EXCERPTS_FOR_CITATIONS]
        ]

        started = _log_step_start("7_store_documents")
        await store_document(document_id, excerpts)
        _log_step_end("7_store_documents", started, timings_ms)

        started = _log_step_start("8_store_chunks")
        await store_chunks(document_id, embedded_chunks)
        _log_step_end("8_store_chunks", started, timings_ms)

        record["status"] = "ready"
        record["chunk_count"] = len(embedded_chunks)
        record["excerpts"] = excerpts
        logger.info("Indexed document %s into %d chunks", document_id, len(embedded_chunks))
    except RagBackendError as error:
        logger.warning("Indexing failed for document %s: %s", document_id, error)
        await postgres_store.update_document(document_id, status="failed", error_message=str(error))
        record["status"] = "failed"
        record["error"] = str(error)
    finally:
        record["step_timings_ms"] = timings_ms
        write_indexing_log(record)
