from __future__ import annotations

from dataclasses import dataclass, field

from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings


@dataclass
class RetrievalState:
    """Per-request context shared by the retrieval steps: who is asking (and so which
    documents are searchable), how the search runs, and what it found along the way.

    The step dataclasses (RawQuery -> EmbeddedQuery -> ScoredChunk ...) still carry the
    data being transformed; this carries what every step needs to know about the request.
    """

    request_id: str
    user: CurrentUser
    document_ids: list[str] | None = None
    search_mode: str = field(
        default_factory=lambda: "hybrid" if settings.hybrid_search_enabled else "vector"
    )
    vector_candidate_count: int | None = None
    text_candidate_count: int | None = None
    permission_dropped_count: int = 0

    @property
    def allowed_classifications(self) -> frozenset[str]:
        return self.user.allowed_classifications

    def to_log(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "user_id": self.user.id,
            "username": self.user.username,
            "role": self.user.role,
            "allowed_classifications": sorted(self.allowed_classifications),
            "document_ids": self.document_ids,
            "search_mode": self.search_mode,
            "vector_candidate_count": self.vector_candidate_count,
            "text_candidate_count": self.text_candidate_count,
            "permission_dropped_count": self.permission_dropped_count,
        }
