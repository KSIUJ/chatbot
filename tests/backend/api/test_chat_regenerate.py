"""
Testy endpointu /chat w zakresie regeneracji odpowiedzi. Warstwa LLM jest
podmieniana na atrape - sprawdzamy wylacznie, co lada w bazie i co dostaje
model jako historia.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
sys.path.insert(0, BACKEND_PARENT)

from backend import main as main_module
from backend.database import get_db
from backend.models import Base, MessageRole


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    calls = []

    def fake_answer(message, history=None, **kwargs):
        calls.append({"message": message, "history": list(history or [])})
        return {"answer": f"odpowiedz na: {message}", "files": []}

    monkeypatch.setattr(main_module, "rag_answer", fake_answer)
    main_module.app.dependency_overrides[get_db] = override_get_db

    with TestClient(main_module.app) as test_client:
        test_client.calls = calls
        test_client.session_factory = Session
        yield test_client

    main_module.app.dependency_overrides.clear()


def _messages(client, conversation_id):
    db = client.session_factory()
    try:
        from backend.database import get_messages

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
