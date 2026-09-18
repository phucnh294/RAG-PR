from __future__ import annotations

import logging

from rag_backend.config import settings
from rag_backend.exceptions import RagBackendError
from rag_backend.rag_pipeline.indexing.step1_load_input import load_input
from rag_backend.rag_pipeline.indexing.step2_document_parsing import parse_document
from rag_backend.rag_pipeline.indexing.step3_chunking_strategy import chunk_text
from rag_backend.rag_pipeline.indexing.step4_preprocessing import preprocess_chunks
from rag_backend.rag_pipeline.indexing.step5_extract_metadata import extract_metadata
from rag_backend.rag_pipeline.indexing.step6_embedding import embed_chunks
from rag_backend.rag_pipeline.indexing.step7_store_documents import store_document
from rag_backend.rag_pipeline.indexing.step8_store_chunks import store_chunks
from rag_backend.storage import dummy_store

logger = logging.getLogger(__name__)

_MAX_EXCERPTS_FOR_CITATIONS = 2


def run_indexing(document_id: str, filename: str, mime_type: str) -> None:
    """Run all 8 indexing steps in order for one already-uploaded document.

    On any domain error (unsupported/unparseable file, etc.), marks the document
    failed with the error message rather than leaving it stuck in "pending" or
    partially indexed (steps 7/8 never run on failure).
    """
    try:
        loaded_file = load_input(document_id, filename, mime_type)
        parsed = parse_document(loaded_file)
        chunks = chunk_text(parsed, settings.chunk_size_words, settings.chunk_overlap_words)
        chunks = preprocess_chunks(chunks)
        chunks_with_metadata = extract_metadata(chunks)
        embedded_chunks = embed_chunks(chunks_with_metadata)

        excerpts = [
            item.chunk.content for item in chunks_with_metadata[:_MAX_EXCERPTS_FOR_CITATIONS]
        ]
        store_document(document_id, excerpts)
        store_chunks(document_id, embedded_chunks)
    except RagBackendError as error:
        logger.warning("Indexing failed for document %s: %s", document_id, error)
        dummy_store.update_document(document_id, status="failed", error_message=str(error))
        return

    logger.info("Indexed document %s into %d chunks", document_id, len(embedded_chunks))
