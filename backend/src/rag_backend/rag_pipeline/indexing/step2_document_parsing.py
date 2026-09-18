from __future__ import annotations

from dataclasses import dataclass

from rag_backend.exceptions import PdfParsingNotImplementedError
from rag_backend.rag_pipeline.indexing.step1_load_input import LoadedFile


@dataclass
class ParsedDocument:
    document_id: str
    filename: str
    mime_type: str
    text: str


def parse_document(loaded_file: LoadedFile) -> ParsedDocument:
    """Extract plain text from the raw bytes according to mime type.

    PDF is intentionally not implemented yet — raises PdfParsingNotImplementedError
    so the orchestrator can mark the document failed instead of silently producing
    empty text.
    """
    if loaded_file.mime_type == "application/pdf":
        raise PdfParsingNotImplementedError(
            f"PDF parsing is not implemented yet (document {loaded_file.document_id})"
        )

    text = loaded_file.raw_bytes.decode("utf-8", errors="replace")
    return ParsedDocument(
        document_id=loaded_file.document_id,
        filename=loaded_file.filename,
        mime_type=loaded_file.mime_type,
        text=text,
    )
