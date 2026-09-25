from __future__ import annotations

from datetime import UTC, datetime

from rag_backend.conversations.models import MessageRecord, Turn
from rag_backend.conversations.service import pair_turns, title_from_question


def _message(role: str, content: str) -> MessageRecord:
    return MessageRecord(
        id=content,
        conversation_id="c1",
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_pair_turns_skips_unanswered_questions() -> None:
    messages = [
        _message("user", "q1"),
        _message("assistant", "a1"),
        _message("user", "q2 (stream died)"),
        _message("user", "q3"),
        _message("assistant", "a3"),
        _message("user", "q4 (being answered now)"),
    ]

    assert pair_turns(messages) == [Turn("q1", "a1"), Turn("q3", "a3")]


def test_title_from_question_is_one_short_line() -> None:
    title = title_from_question("  What   is\nthe leave policy " + "x" * 100)

    assert "\n" not in title
    assert len(title) == 60
    assert title.endswith("…")
    assert title_from_question("   ") == "New chat"
