from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from rag_backend.config import settings
from rag_backend.llm_model.client import LlmClient

_LEAVE_QUESTION = "All employees are entitled to 20 days of paid annual leave per calendar year."


class RecordingLlmClient(LlmClient):
    """Answers every chat with fixed tokens, rewrites follow-ups to a fixed standalone
    question, and records what each call was sent."""

    def __init__(self, tokens: list[str], rewrite: str = _LEAVE_QUESTION) -> None:
        self._tokens = tokens
        self._rewrite = rewrite
        self.chat_calls: list[list[dict[str, str]]] = []
        self.rewrite_calls: list[list[dict[str, str]]] = []

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        self.chat_calls.append(messages)
        for token in self._tokens:
            yield token

    async def complete_chat(self, messages: list[dict[str, str]]) -> str:
        self.rewrite_calls.append(messages)
        return self._rewrite


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> RecordingLlmClient:
    fake = RecordingLlmClient(tokens=["Employees ", "get ", "20 ", "days."])
    monkeypatch.setattr("rag_backend.llm_model.client.llm_client", fake)
    return fake


def _payload(body: str) -> dict[str, object]:
    return json.loads(body.partition("\x00CITATIONS:")[2])


def _retrieval(body: str) -> dict[str, object]:
    retrieval = _payload(body)["retrieval"]
    assert isinstance(retrieval, dict)
    return retrieval


# --- conversations CRUD ---


def test_create_list_get_and_delete_a_conversation(client: TestClient) -> None:
    created = client.post("/conversations", json={"title": "Leave questions"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    listed = client.get("/conversations").json()
    assert [item["id"] for item in listed] == [conversation_id]

    detail = client.get(f"/conversations/{conversation_id}").json()
    assert detail["title"] == "Leave questions"
    assert detail["messages"] == []

    assert client.delete(f"/conversations/{conversation_id}").status_code == 204
    assert client.get(f"/conversations/{conversation_id}").status_code == 404


def test_conversations_are_private_to_their_owner_even_for_admins(
    client: TestClient, role_headers: dict[str, dict[str, str]]
) -> None:
    staff_conversation = client.post(
        "/conversations", json={}, headers=role_headers["staff"]
    ).json()
    conversation_id = staff_conversation["id"]
    assert staff_conversation["title"] == "New chat"

    # The admin (default client identity) sees neither it in the list nor its content.
    assert client.get("/conversations").json() == []
    assert client.get(f"/conversations/{conversation_id}").status_code == 404
    assert client.delete(f"/conversations/{conversation_id}").status_code == 404
    other_user = client.get(f"/conversations/{conversation_id}", headers=role_headers["user"])
    assert other_user.status_code == 404


# --- chat + conversations ---


def test_chat_without_conversation_id_creates_one_and_saves_the_exchange(
    client: TestClient, llm: RecordingLlmClient
) -> None:
    response = client.post("/chat", json={"message": _LEAVE_QUESTION})

    conversation_id = response.headers["X-Conversation-Id"]
    assert _payload(response.text)["conversation_id"] == conversation_id
    detail = client.get(f"/conversations/{conversation_id}").json()
    assert detail["title"].startswith("All employees are entitled")
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    answer = detail["messages"][1]
    assert answer["content"] == "Employees get 20 days."
    assert "employee_handbook.md" in json.dumps(answer["payload"]["citations"])


def test_chat_with_someone_elses_conversation_id_is_a_404(
    client: TestClient, role_headers: dict[str, dict[str, str]], llm: RecordingLlmClient
) -> None:
    staff_conversation = client.post(
        "/conversations", json={}, headers=role_headers["staff"]
    ).json()

    response = client.post(
        "/chat", json={"message": "hello", "conversation_id": staff_conversation["id"]}
    )
    unknown = client.post(
        "/chat",
        json={"message": "hello", "conversation_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404
    assert unknown.status_code == 404
    assert llm.chat_calls == []


def test_follow_up_is_contextualized_and_sent_with_the_history(
    client: TestClient, llm: RecordingLlmClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    first = client.post("/chat", json={"message": "How much annual leave do we get?"})
    conversation_id = first.headers["X-Conversation-Id"]

    follow_up = client.post(
        "/chat", json={"message": "and is it per year?", "conversation_id": conversation_id}
    )

    retrieval = _retrieval(follow_up.text)
    assert retrieval["history_turns_used"] == 1
    assert retrieval["standalone_question"] == _LEAVE_QUESTION
    assert "Follow-up question: and is it per year?" in llm.rewrite_calls[0][1]["content"]
    sent = llm.chat_calls[1]
    assert sent[1] == {"role": "user", "content": "How much annual leave do we get?"}
    assert sent[2] == {"role": "assistant", "content": "Employees get 20 days."}
    assert sent[3] == {"role": "user", "content": _LEAVE_QUESTION}
    saved = client.get(f"/conversations/{conversation_id}").json()["messages"]
    assert saved[3]["standalone_question"] == _LEAVE_QUESTION


def test_memory_disabled_sends_no_history_and_skips_the_rewrite(
    client: TestClient, llm: RecordingLlmClient
) -> None:
    first = client.post("/chat", json={"message": "How much annual leave do we get?"})
    conversation_id = first.headers["X-Conversation-Id"]

    client.post(
        "/chat",
        json={
            "message": "and is it per year?",
            "conversation_id": conversation_id,
            "memory_enabled": False,
        },
    )

    assert llm.rewrite_calls == []
    assert [message["role"] for message in llm.chat_calls[1]] == ["system", "user"]


def test_memory_turns_limits_how_many_turns_are_sent(
    client: TestClient, llm: RecordingLlmClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "semantic_cache_enabled", False)
    conversation_id = client.post("/chat", json={"message": "first question"}).headers[
        "X-Conversation-Id"
    ]
    for question in ("second question", "third question"):
        client.post("/chat", json={"message": question, "conversation_id": conversation_id})

    response = client.post(
        "/chat",
        json={"message": "fourth question", "conversation_id": conversation_id, "memory_turns": 1},
    )

    assert _retrieval(response.text)["history_turns_used"] == 1
    assert llm.chat_calls[-1][1] == {"role": "user", "content": "third question"}


# --- semantic cache through the API ---


def test_repeated_question_is_served_from_the_cache_without_calling_the_llm(
    client: TestClient, llm: RecordingLlmClient
) -> None:
    first = client.post("/chat", json={"message": _LEAVE_QUESTION})
    second = client.post("/chat", json={"message": _LEAVE_QUESTION})

    assert _retrieval(first.text)["cache_status"] == "miss"
    assert _retrieval(second.text)["cache_status"] == "hit"
    assert second.text.partition("\x00CITATIONS:")[0] == "Employees get 20 days."
    assert _payload(second.text)["citations"] == _payload(first.text)["citations"]
    assert len(llm.chat_calls) == 1
    conversation_id = second.headers["X-Conversation-Id"]
    saved = client.get(f"/conversations/{conversation_id}").json()["messages"]
    assert saved[-1]["cache_hit"] is True


def test_cached_answer_is_not_served_to_a_different_role(
    client: TestClient, llm: RecordingLlmClient, role_headers: dict[str, dict[str, str]]
) -> None:
    client.post("/chat", json={"message": _LEAVE_QUESTION}, headers=role_headers["staff"])

    as_user = client.post("/chat", json={"message": _LEAVE_QUESTION}, headers=role_headers["user"])
    as_staff = client.post(
        "/chat", json={"message": _LEAVE_QUESTION}, headers=role_headers["staff"]
    )

    assert _retrieval(as_user.text)["cache_status"] == "miss"
    assert _retrieval(as_staff.text)["cache_status"] == "hit"


def test_uploading_a_document_invalidates_cached_answers_that_could_read_it(
    client: TestClient, llm: RecordingLlmClient
) -> None:
    client.post("/chat", json={"message": _LEAVE_QUESTION})
    upload = client.post(
        "/documents",
        files={"file": ("leave_update.txt", b"Annual leave is now 25 days.", "text/plain")},
        data={"classification": "public"},
    )
    assert upload.status_code == 200

    again = client.post("/chat", json={"message": _LEAVE_QUESTION})

    assert _retrieval(again.text)["cache_status"] == "miss"
    assert len(llm.chat_calls) == 2


def test_deleting_a_cited_document_invalidates_the_cached_answer(
    client: TestClient, llm: RecordingLlmClient
) -> None:
    first = client.post("/chat", json={"message": _LEAVE_QUESTION})
    cited = _payload(first.text)["citations"]
    assert isinstance(cited, list)
    assert client.delete(f"/documents/{cited[0]['document_id']}").status_code == 204

    again = client.post("/chat", json={"message": _LEAVE_QUESTION})

    assert _retrieval(again.text)["cache_status"] == "miss"


def test_unanswerable_question_is_not_cached(client: TestClient, llm: RecordingLlmClient) -> None:
    question = "zzz qqq xxx completely unrelated gibberish yyy www"
    client.post("/chat", json={"message": question})
    again = client.post("/chat", json={"message": question})

    assert _retrieval(again.text)["cache_status"] == "miss"


def test_admin_can_clear_the_cache_and_others_cannot(
    client: TestClient, llm: RecordingLlmClient, role_headers: dict[str, dict[str, str]]
) -> None:
    client.post("/chat", json={"message": _LEAVE_QUESTION})

    assert client.delete("/cache", headers=role_headers["staff"]).status_code == 403
    cleared = client.delete("/cache")

    assert cleared.status_code == 200
    assert cleared.json() == {"deleted": 1}
