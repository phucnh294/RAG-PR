from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from rag_backend.auth.models import CurrentUser
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.storage import dummy_store
from rag_backend.storage.records import DocumentRecord

RegisterDocument = Callable[..., DocumentRecord]


@pytest.fixture
def register_document() -> RegisterDocument:
    """Put a document with a chosen id into the fake store, so chunks added under that id
    are searchable (the fake, like the real permission view, only returns chunks whose
    document exists and whose classification the user may read)."""

    def _register(document_id: str, classification: str = "internal") -> DocumentRecord:
        record = DocumentRecord(
            id=document_id,
            filename=f"{document_id}.md",
            content_hash=document_id,
            mime_type="text/markdown",
            size_bytes=1,
            status="ready",
            created_at=datetime.now(UTC),
            classification=classification,
        )
        dummy_store._documents[document_id] = record
        return record

    return _register


def make_state(user: CurrentUser, document_ids: list[str] | None = None) -> RetrievalState:
    return RetrievalState(request_id="test-request", user=user, document_ids=document_ids)


@pytest.fixture
def admin_state(auth_users: dict[str, CurrentUser]) -> RetrievalState:
    return make_state(auth_users["admin"])
