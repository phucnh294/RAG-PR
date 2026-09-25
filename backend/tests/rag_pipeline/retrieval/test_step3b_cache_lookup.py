from __future__ import annotations

import pytest

from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.embedding_model import client as embedding_model_client
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import EmbeddedQuery
from rag_backend.rag_pipeline.retrieval.step3b_cache_lookup import cache_lookup
from rag_backend.semantic_cache import repository as cache_repository
from rag_backend.semantic_cache import service as semantic_cache_service
from rag_backend.storage import dummy_store
from tests.rag_pipeline.retrieval.conftest import RegisterDocument, make_state

_QUESTION = "how many days of paid annual leave do employees get"
_EVIDENCE = {
    "level": "high",
    "top_score": 0.9,
    "mean_score": 0.9,
    "surviving_chunk_count": 1,
    "threshold": 0.7,
}


async def _embedded(text: str = _QUESTION, document_ids: list[str] | None = None) -> EmbeddedQuery:
    embedding = await embedding_model_client.embedding_client.embed_text(text)
    return EmbeddedQuery(text=text, embedding=embedding, document_ids=document_ids)


async def _store(user: CurrentUser, document_id: str, question: str = _QUESTION) -> str:
    embedded = await _embedded(question)
    return await semantic_cache_service.store(
        question=question,
        embedding=embedded.embedding,
        answer="Employees get 20 days.",
        citations=[
            {
                "document_id": document_id,
                "filename": f"{document_id}.md",
                "excerpt": "20 days",
                "similarity_score": 0.9,
                "rerank_score": None,
            }
        ],
        evidence=_EVIDENCE,
        user=user,
    )


async def test_cache_lookup_hits_for_the_same_access_scope(
    auth_users: dict[str, CurrentUser], register_document: RegisterDocument
) -> None:
    register_document("doc-internal", classification="internal")
    entry_id = await _store(auth_users["staff"], "doc-internal")
    state = make_state(auth_users["staff"])

    hit = await cache_lookup(await _embedded(), state)

    assert hit is not None and hit.id == entry_id
    assert state.cache_status == "hit"
    assert state.cache_similarity == pytest.approx(1.0)
    assert dummy_store._cache[entry_id].hit_count == 1


async def test_cache_lookup_misses_for_a_higher_clearance_scope(
    auth_users: dict[str, CurrentUser], register_document: RegisterDocument
) -> None:
    # The manager could read the cited doc, but the answer was built from the staff
    # corpus only — a manager must get an answer from everything they can read.
    register_document("doc-internal", classification="internal")
    await _store(auth_users["staff"], "doc-internal")
    state = make_state(auth_users["manager"])

    assert await cache_lookup(await _embedded(), state) is None
    assert state.cache_status == "miss"


async def test_cache_lookup_misses_for_a_lower_clearance_scope(
    auth_users: dict[str, CurrentUser], register_document: RegisterDocument
) -> None:
    register_document("doc-confidential", classification="confidential")
    await _store(auth_users["manager"], "doc-confidential")

    for role in ("user", "staff"):
        state = make_state(auth_users[role])
        assert await cache_lookup(await _embedded(), state) is None
        assert state.cache_status == "miss"


async def test_cache_lookup_misses_when_a_cited_document_was_deleted(
    auth_users: dict[str, CurrentUser], register_document: RegisterDocument
) -> None:
    register_document("doc-internal", classification="internal")
    await _store(auth_users["staff"], "doc-internal")
    del dummy_store._documents["doc-internal"]
    state = make_state(auth_users["staff"])

    assert await cache_lookup(await _embedded(), state) is None
    assert state.cache_status == "miss"


async def test_cache_lookup_rechecks_access_live_even_with_a_stale_user_snapshot(
    auth_users: dict[str, CurrentUser], register_document: RegisterDocument
) -> None:
    # The CurrentUser still lists "internal" (same scope as the entry), but the grant was
    # revoked in the database: the live permission-view check must refuse the entry.
    register_document("doc-internal", classification="internal")
    await _store(auth_users["staff"], "doc-internal")
    await dummy_store.revoke_access("staff", "internal")
    state = make_state(auth_users["staff"])

    assert await cache_lookup(await _embedded(), state) is None


async def test_cache_lookup_misses_below_the_similarity_threshold(
    auth_users: dict[str, CurrentUser], register_document: RegisterDocument
) -> None:
    register_document("doc-internal", classification="internal")
    await _store(auth_users["staff"], "doc-internal")
    state = make_state(auth_users["staff"])

    different = await _embedded("who approves travel expense reports")

    assert await cache_lookup(different, state) is None
    assert state.cache_status == "miss"


async def test_cache_lookup_ignores_expired_entries(
    auth_users: dict[str, CurrentUser],
    register_document: RegisterDocument,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_document("doc-internal", classification="internal")
    monkeypatch.setattr(settings, "cache_ttl_seconds", -1)
    await _store(auth_users["staff"], "doc-internal")

    assert await cache_lookup(await _embedded(), make_state(auth_users["staff"])) is None


async def test_cache_lookup_ignores_entries_written_by_another_answer_model(
    auth_users: dict[str, CurrentUser],
    register_document: RegisterDocument,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_document("doc-internal", classification="internal")
    await _store(auth_users["staff"], "doc-internal")
    monkeypatch.setattr(settings, "llm_model_name", "some-other-model")

    assert await cache_lookup(await _embedded(), make_state(auth_users["staff"])) is None


async def test_cache_lookup_is_bypassed_for_a_document_filter_or_an_opt_out(
    auth_users: dict[str, CurrentUser], register_document: RegisterDocument
) -> None:
    register_document("doc-internal", classification="internal")
    await _store(auth_users["staff"], "doc-internal")

    filtered = make_state(auth_users["staff"], document_ids=["doc-internal"])
    assert await cache_lookup(await _embedded(document_ids=["doc-internal"]), filtered) is None
    assert filtered.cache_status == "bypassed"

    opted_out = make_state(auth_users["staff"])
    assert await cache_lookup(await _embedded(), opted_out, use_cache=False) is None
    assert opted_out.cache_status == "bypassed"


async def test_cache_lookup_reports_disabled_when_the_setting_is_off(
    auth_users: dict[str, CurrentUser], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    state = make_state(auth_users["staff"])

    assert await cache_lookup(await _embedded(), state) is None
    assert state.cache_status == "disabled"


async def test_cache_lookup_treats_a_cache_outage_as_a_miss(
    auth_users: dict[str, CurrentUser], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _unreachable(*args: object) -> list[object]:
        raise OSError("connection refused")

    monkeypatch.setattr(cache_repository, "find_cache_candidates", _unreachable)
    state = make_state(auth_users["staff"])

    assert await cache_lookup(await _embedded(), state) is None
    assert state.cache_status == "error"
