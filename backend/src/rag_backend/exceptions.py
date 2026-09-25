class RagBackendError(Exception):
    """Base class for domain errors raised by the RAG backend."""


class UnsupportedFileTypeError(RagBackendError):
    """Raised when an uploaded file's MIME type is not in the allowed list."""


class FileTooLargeError(RagBackendError):
    """Raised when an uploaded file exceeds the configured size limit."""


class DocumentNotFoundError(RagBackendError):
    """Raised when a requested document id does not exist."""


class DocumentParsingError(RagBackendError):
    """Raised when a document's raw bytes cannot be parsed into text."""


class PdfParsingNotImplementedError(DocumentParsingError):
    """Raised for PDF uploads until real PDF text extraction is implemented."""


class GuardrailJudgeError(RagBackendError):
    """Raised when the guardrail judge LLM is unreachable or times out.

    Always caught inside rag_backend.guardrails.judge_client.judge() and converted to
    a fail-closed GuardrailVerdict — never propagates to a route handler or produces
    an HTTP error response.
    """
