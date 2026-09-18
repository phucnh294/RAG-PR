class RagBackendError(Exception):
    """Base class for domain errors raised by the RAG backend."""


class UnsupportedFileTypeError(RagBackendError):
    """Raised when an uploaded file's MIME type is not in the allowed list."""


class FileTooLargeError(RagBackendError):
    """Raised when an uploaded file exceeds the configured size limit."""


class DocumentNotFoundError(RagBackendError):
    """Raised when a requested document id does not exist."""
