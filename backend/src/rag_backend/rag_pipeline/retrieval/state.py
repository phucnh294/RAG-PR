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
    rerank_enabled: bool = field(default_factory=lambda: settings.rerank_enabled_default)
    # "disabled" (not requested), "applied", "failed" (reranker error -> hybrid order kept)
    # or "skipped" (requested but nothing to rerank).
    rerank_status: str = "disabled"
    rerank_candidate_count: int | None = None
    rerank_duration_ms: float | None = None
    conversation_id: str | None = None
    memory_enabled: bool = field(default_factory=lambda: settings.memory_enabled_default)
    memory_turns: int = field(default_factory=lambda: settings.memory_turns_default)
    history_turns_used: int = 0
    # The question retrieval and the cache actually used: the step-2c rewrite of a
    # follow-up, or the normalized question when nothing was rewritten.
    standalone_question: str | None = None
    # "disabled" (setting off), "bypassed" (this request opted out, e.g. evals or a
    # document filter), "miss", "hit" or "error" (cache table unreachable -> miss).
    cache_status: str = "disabled"
    cache_similarity: float | None = None
    cache_entry_id: str | None = None

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
            "rerank_enabled": self.rerank_enabled,
            "rerank_status": self.rerank_status,
            "rerank_candidate_count": self.rerank_candidate_count,
            "rerank_duration_ms": self.rerank_duration_ms,
            "conversation_id": self.conversation_id,
            "memory_enabled": self.memory_enabled,
            "memory_turns": self.memory_turns,
            "history_turns_used": self.history_turns_used,
            "standalone_question": self.standalone_question,
            "cache_status": self.cache_status,
            "cache_similarity": self.cache_similarity,
            "cache_entry_id": self.cache_entry_id,
        }
