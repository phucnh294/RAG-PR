from __future__ import annotations

import logging

import pytest

from rag_backend.auth.models import CurrentUser
from rag_backend.rag_pipeline.retrieval.state import RetrievalState
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.rag_pipeline.retrieval.step4_similarity_search import ScoredChunk
from rag_backend.rag_pipeline.retrieval.step5_metadata_filter import apply_metadata_filter
from rag_backend.storage import dummy_store
from tests.rag_pipeline.retrieval.conftest import make_state


def _scored_chunk(document_id: str, classification: str | None = "public") -> ScoredChunk:
    chunk = dummy_store.ChunkRecord(
        id=f"chunk-{document_id}",
        document_id=document_id,
        chunk_index=0,
        content="text",
        embedding=[1.0],
        metadata={"word_count": 1, "char_count": 4},
        classification=classification,
    )
    return ScoredChunk(chunk=chunk, similarity_score=0.9)


def test_apply_metadata_filter_is_noop_without_document_ids(admin_state: RetrievalState) -> None:
    chunks = [_scored_chunk("doc-1"), _scored_chunk("doc-2")]
    query = EmbeddedQuery(text="q", embedding=[1.0], document_ids=None)

    assert apply_metadata_filter(chunks, query, admin_state) == chunks


def test_apply_metadata_filter_restricts_to_allowed_documents(
    admin_state: RetrievalState,
) -> None:
    chunks = [_scored_chunk("doc-1"), _scored_chunk("doc-2")]
    query = EmbeddedQuery(text="q", embedding=[1.0], document_ids=["doc-2"])

    filtered = apply_metadata_filter(chunks, query, admin_state)

    assert [item.chunk.document_id for item in filtered] == ["doc-2"]


def test_apply_metadata_filter_drops_chunks_outside_user_clearance(
    auth_users: dict[str, CurrentUser], caplog: pytest.LogCaptureFixture
) -> None:
    state = make_state(auth_users["user"])
    chunks = [
        _scored_chunk("doc-public", "public"),
        _scored_chunk("doc-secret", "confidential"),
        _scored_chunk("doc-unknown", None),
    ]
    query = EmbeddedQuery(text="q", embedding=[1.0])

    with caplog.at_level(logging.WARNING):
        filtered = apply_metadata_filter(chunks, query, state)

    assert [item.chunk.document_id for item in filtered] == ["doc-public"]
    assert state.permission_dropped_count == 2
    assert any("Permission filter dropped 2" in message for message in caplog.messages)
