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


class EmbeddingModelError(RagBackendError):
    """Raised when the embedding-model container is unreachable, times out, or errors.

    A RagBackendError so run_indexing marks the document "failed" with this message
    instead of leaving it stuck in "pending" with no chunks.
    """


class RerankerModelError(RagBackendError):
    """Raised when the reranker-model container is unreachable, times out, errors, or
    returns a malformed response.

    Step 6 catches it and falls back to the hybrid (RRF) order, so a reranker outage
    degrades ranking quality but never fails a chat request.
    """


class ConversationNotFoundError(RagBackendError):
    """Raised when a conversation id does not exist OR belongs to another user (HTTP 404,
    so the API never confirms that someone else's conversation exists)."""


class SemanticCacheError(RagBackendError):
    """Raised when the semantic cache table cannot be read or written.

    The retrieval pipeline treats it as a cache miss (lookup) or a skipped store, so a
    cache outage only costs latency, never a failed chat request.
    """


class AuthError(RagBackendError):
    """Base class for authentication/authorization failures."""


class UnknownUserError(AuthError):
    """Raised when a request names a user id that does not exist (maps to HTTP 401)."""


class InactiveUserError(AuthError):
    """Raised when a request names a deactivated user (maps to HTTP 403)."""


class PermissionDeniedError(AuthError):
    """Raised when an authenticated user may not perform an action (maps to HTTP 403)."""


class UserAlreadyExistsError(AuthError):
    """Raised when creating a user whose username is taken (maps to HTTP 409)."""


class InvalidRoleError(AuthError):
    """Raised when a role name is not one of the configured roles (maps to HTTP 422)."""


class InvalidClassificationError(AuthError):
    """Raised when a classification name is not a known classification (maps to HTTP 422)."""


class GuardrailJudgeError(RagBackendError):
    """Raised when the guardrail judge LLM is unreachable or times out.

    Always caught inside rag_backend.guardrails.judge_client.judge() and converted to
    a fail-closed GuardrailVerdict — never propagates to a route handler or produces
    an HTTP error response.
    """
