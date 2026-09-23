from __future__ import annotations

import logging
from typing import Any

from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.exceptions import RagBackendError
from rag_backend.pipeline_logging import StepRecorder, write_indexing_log
from rag_backend.rag_pipeline.indexing.step1_load_input import load_input
from rag_backend.rag_pipeline.indexing.step2_document_parsing import parse_document
from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import chunk_text
from rag_backend.rag_pipeline.indexing.step4_preprocessing import preprocess_chunks
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import extract_metadata
from rag_backend.rag_pipeline.indexing.step6_embedding import embed_chunks
from rag_backend.rag_pipeline.indexing.step7_store_documents import store_document
from rag_backend.rag_pipeline.indexing.step8_store_chunks import store_chunks

logger = logging.getLogger(__name__)

_PROCESS_NAME = "Indexing"
_MAX_EXCERPTS_FOR_CITATIONS = 2


async def run_indexing(document_id: str, filename: str, mime_type: str) -> None:
    """Run all 8 indexing steps in order for one already-uploaded document.

    On any domain error (unsupported/unparseable file, etc.), marks the document
    failed with the error message rather than leaving it stuck in "pending" or
    partially indexed (steps 7/8 never run on failure) — the step that raised will
    show an "input" log line with no matching "output" line, making the failure
    point visible from the console/log file alone.

    Every step logs its input AND its output as separate console lines
    ("Indexing - {step} {timestamp} - input/output: {data}"); the same data lands
    in a JSON file under pipeline-logs/indexing/ (see StepRecorder), mirroring the
    retrieval pipeline's per-request logs.
    """
    record: dict[str, Any] = {
        "document_id": document_id,
        "filename": filename,
        "mime_type": mime_type,
        "steps": {},
    }
    steps = StepRecorder(logger, _PROCESS_NAME, record)
    embedded_chunks: list[Any] = []
    try:
        steps.log_input(
            "1_load_input",
            {"document_id": document_id, "filename": filename, "mime_type": mime_type},
        )
        loaded_file = load_input(document_id, filename, mime_type)
        steps.log_output("1_load_input", {"raw_bytes": len(loaded_file.raw_bytes)})

        steps.log_input(
            "2_document_parsing",
            {"raw_bytes": len(loaded_file.raw_bytes), "mime_type": loaded_file.mime_type},
        )
        parsed = parse_document(loaded_file)
        steps.log_output("2_document_parsing", {"parsed_text_chars": len(parsed.text)})

        steps.log_input(
            "3_chunking_strategy",
            {
                "parsed_text_chars": len(parsed.text),
                "chunk_size_words": settings.chunk_size_words,
                "chunk_overlap_words": settings.chunk_overlap_words,
            },
        )
        chunks = chunk_text(parsed, settings.chunk_size_words, settings.chunk_overlap_words)
        steps.log_output("3_chunking_strategy", {"chunk_count": len(chunks)})

        steps.log_input("4_preprocessing", {"chunk_count": len(chunks)})
        chunks = preprocess_chunks(chunks)
        steps.log_output("4_preprocessing", {"chunk_count": len(chunks)})

        steps.log_input("5_extract_metadata", {"chunk_count": len(chunks)})
        chunks_with_metadata = extract_metadata(chunks)
        steps.log_output("5_extract_metadata", {"chunk_count": len(chunks_with_metadata)})

        steps.log_input("6_embedding", {"chunk_count": len(chunks_with_metadata)})
        embedded_chunks = await embed_chunks(chunks_with_metadata)
        steps.log_output(
            "6_embedding",
            {
                "chunk_count": len(embedded_chunks),
                "embedding_dimension": (
                    len(embedded_chunks[0].embedding) if embedded_chunks else 0
                ),
            },
        )

        excerpts = [
            item.chunk.content for item in chunks_with_metadata[:_MAX_EXCERPTS_FOR_CITATIONS]
        ]

        steps.log_input(
            "7_store_documents", {"document_id": document_id, "excerpt_count": len(excerpts)}
        )
        await store_document(document_id, excerpts)
        steps.log_output("7_store_documents", {"status": "ready", "excerpts": excerpts})

        steps.log_input(
            "8_store_chunks",
            {"document_id": document_id, "chunk_count": len(embedded_chunks)},
        )
        await store_chunks(document_id, embedded_chunks)
        steps.log_output("8_store_chunks", {"stored_chunk_count": len(embedded_chunks)})

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
        write_indexing_log(record)
