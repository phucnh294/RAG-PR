from __future__ import annotations

from rag_backend.config import settings
from rag_backend.rag_pipeline.retrieval.step2_normalize_input import NormalizedQuery
from rag_backend.rag_pipeline.retrieval.step3_embedding_question import embed_question


async def test_embed_question_produces_vector_of_configured_dimension() -> None:
    query = NormalizedQuery(text="how many days of leave")

    embedded = await embed_question(query)

    assert len(embedded.embedding) == settings.embedding_dimension
    assert embedded.text == "how many days of leave"


async def test_embed_question_is_deterministic() -> None:
    query = NormalizedQuery(text="same question")

    first = await embed_question(query)
    second = await embed_question(query)

    assert first.embedding == second.embedding
