"""
Testy endpointu /chat w zakresie regeneracji odpowiedzi. Warstwa LLM jest
podmieniana na atrape - sprawdzamy wylacznie, co lada w bazie i co dostaje
model jako historia.
"""

import pytest

from src.backend import main as main_module
from src.backend.models import MessageRole


@pytest.fixture
def client(client, member_override):
    """Klient z conftest + staly zalogowany czlonek (logowanie ma osobne testy)."""
    return client


def _messages(client, conversation_id):
    db = client.session_factory()
    try:
        from src.backend.database import get_messages

        return [(m.role, m.content) for m in get_messages(db, conversation_id)]
    finally:
        db.close()


def test_normal_turn_appends_question_and_answer(client):
    r = client.post("/chat", json={"message": "kim jest Jan Kowalski"})
    cid = r.json()["conversation_id"]

    assert _messages(client, cid) == [
        (MessageRole.USER, "kim jest Jan Kowalski"),
        (MessageRole.ASSISTANT, "odpowiedz na: kim jest Jan Kowalski"),
    ]


def test_regenerate_replaces_answer_without_duplicating_question(client):
    cid = client.post("/chat", json={"message": "kim jest Jan Kowalski"}).json()["conversation_id"]

    client.post(
        "/chat",
        json={"message": "kim jest Jan Kowalski", "conversation_id": cid, "regenerate": True},
    )

    stored = _messages(client, cid)
    assert len(stored) == 2
    assert stored[0] == (MessageRole.USER, "kim jest Jan Kowalski")
    assert stored[1][0] == MessageRole.ASSISTANT


def test_regenerate_does_not_feed_rejected_answer_as_history(client):
    cid = client.post("/chat", json={"message": "kim jest Jan Kowalski"}).json()["conversation_id"]

    client.post(
        "/chat",
        json={"message": "kim jest Jan Kowalski", "conversation_id": cid, "regenerate": True},
    )

    assert client.calls[-1]["history"] == []


def test_followup_after_regenerate_sees_single_clean_exchange(client):
    cid = client.post("/chat", json={"message": "kim jest Jan Kowalski"}).json()["conversation_id"]
    client.post(
        "/chat",
        json={"message": "kim jest Jan Kowalski", "conversation_id": cid, "regenerate": True},
    )

    client.post("/chat", json={"message": "a jakie ma dyzury?", "conversation_id": cid})

    history = client.calls[-1]["history"]
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "kim jest Jan Kowalski"


def test_regenerate_on_new_conversation_still_logs_question(client):
    r = client.post("/chat", json={"message": "kim jest Jan Kowalski", "regenerate": True})
    cid = r.json()["conversation_id"]

    assert _messages(client, cid) == [
        (MessageRole.USER, "kim jest Jan Kowalski"),
        (MessageRole.ASSISTANT, "odpowiedz na: kim jest Jan Kowalski"),
    ]


def _break_llm(monkeypatch):
    def broken_llm(message, history=None, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(main_module, "rag_answer", broken_llm)


def test_failed_followup_leaves_conversation_unchanged(client, monkeypatch):
    cid = client.post("/chat", json={"message": "kim jest Jan Kowalski"}).json()["conversation_id"]
    before = _messages(client, cid)
    working_llm = main_module.rag_answer
    _break_llm(monkeypatch)

    with pytest.raises(RuntimeError):
        client.post("/chat", json={"message": "a jakie ma dyzury?", "conversation_id": cid})

    assert _messages(client, cid) == before
    assert client.get("/stats").json()["total_prompts"] == 1

    # ponowienie po awarii dostaje czysta historie, bez wiszacego pytania
    monkeypatch.setattr(main_module, "rag_answer", working_llm)
    client.post("/chat", json={"message": "a jakie ma dyzury?", "conversation_id": cid})
    assert [m["role"] for m in client.calls[-1]["history"]] == ["user", "assistant"]
    assert len(_messages(client, cid)) == 4


def test_failed_regenerate_keeps_previous_answer(client, monkeypatch):
    cid = client.post("/chat", json={"message": "kim jest Jan Kowalski"}).json()["conversation_id"]
    before = _messages(client, cid)
    _break_llm(monkeypatch)

    with pytest.raises(RuntimeError):
        client.post(
            "/chat",
            json={"message": "kim jest Jan Kowalski", "conversation_id": cid, "regenerate": True},
        )

    assert _messages(client, cid) == before
