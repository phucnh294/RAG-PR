from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import pytest

from rag_backend.embedding_model.client import embedding_client
from rag_backend.llm_model.client import LlmClient
from rag_backend.rag_pipeline.retrieval.pipeline import run_retrieval
from rag_backend.rag_pipeline.retrieval.step10_response import CITATIONS_MARKER
from rag_backend.storage import dummy_store


class FakeLlmClient(LlmClient):
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        for token in self._tokens:
            yield token


async def test_run_retrieval_streams_answer_and_citations_for_a_matching_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rag_backend.llm_model.client.llm_client", FakeLlmClient(tokens=["yes ", "20 ", "days"])
    )
    doc = await dummy_store.add_document(
        filename="handbook.md", content_hash="h1", mime_type="text/markdown", size_bytes=10
    )
    chunk_content = "Employees get 20 days of annual leave per year."
    await dummy_store.add_chunks(
        doc.id,
        [
            dummy_store.ChunkRecord(
                id="chunk-1",
                document_id=doc.id,
                chunk_index=0,
                content=chunk_content,
                embedding=embedding_client.embed_text(chunk_content),
                metadata={"word_count": 8, "char_count": 40},
            )
        ],
    )

    chunks = [chunk async for chunk in run_retrieval(chunk_content)]
    body = b"".join(chunks).decode("utf-8")

    answer_part, _, citations_part = body.partition(CITATIONS_MARKER)
    assert answer_part == "yes 20 days"
    assert "handbook.md" in citations_part


async def test_run_retrieval_logs_each_step_and_the_system_prompt(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("rag_backend.llm_model.client.llm_client", FakeLlmClient(tokens=["ok"]))

    with caplog.at_level(logging.INFO, logger="rag_backend.rag_pipeline.retrieval.pipeline"):
        _ = [chunk async for chunk in run_retrieval("anything")]

    messages = [record.message for record in caplog.records]
    assert any("Retrieval step start: 1_get_input" in m for m in messages)
    assert any("Retrieval step done: 1_get_input" in m for m in messages)
    assert any("Retrieval step start: 9_call_llm_model" in m for m in messages)
    assert any("Retrieval step done: 9_call_llm_model" in m for m in messages)
    assert any("System prompt for this request" in m for m in messages)
