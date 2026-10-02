"""
Oceny (lapki) i zgloszenia odpowiedzi: PUT /messages/{id}/feedback, stan
oceny w GET /conversations/{id} i kopia pytania/odpowiedzi, ktora przezywa
usuniecie rozmowy.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.backend.history import purge_expired_conversations
from src.backend.models import Conversation, Message, MessageFeedback, MessageRole, User

from fake_keycloak import login


def _rows(client) -> list[MessageFeedback]:
    db = client.session_factory()
    try:
        return list(db.execute(select(MessageFeedback).order_by(MessageFeedback.created_at)).scalars())
    finally:
        db.close()


def _ask(client, message: str, conversation_id: str | None = None, **extra) -> dict:
    payload = {"message": message, **extra}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    r = client.post("/chat", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _answer(client, question: str = "Kiedy sesja?") -> tuple[str, str]:
    """Zadaje pytanie; zwraca (id rozmowy, id odpowiedzi)."""
    body = _ask(client, question)
    return body["conversation_id"], body["message"]["id"]


def _put(client, message_id: str, payload: dict):
    return client.put(f"/messages/{message_id}/feedback", json=payload)


@pytest.fixture
def alice(client):
    login(client, client.keycloak, "alice")
    return client


# --- dostep ----------------------------------------------------------------

def test_feedback_requires_login(client):
    assert _put(client, "a" * 32, {"rating": 1}).status_code == 401


def test_unknown_message_is_404(alice):
    assert _put(alice, "f" * 32, {"rating": 1}).status_code == 404


def test_question_cannot_be_rated(alice):
    conversation_id, _ = _answer(alice)
    question = alice.get(f"/conversations/{conversation_id}").json()["messages"][0]
    assert question["role"] == "user"

    assert _put(alice, question["id"], {"rating": 1}).status_code == 404
    assert _rows(alice) == []


def test_someone_elses_answer_looks_like_missing(alice):
    db = alice.session_factory()
    bob = User(oidc_sub="bob")
    db.add(bob)
    db.flush()
    conversation = Conversation(user_id=bob.id)
    db.add(conversation)
    db.flush()
    answer = Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="tajne", sources=[])
    db.add(answer)
    db.commit()
    answer_id = answer.id
    db.close()

    r = _put(alice, answer_id, {"rating": -1})

    assert r.status_code == 404
    assert r.json()["detail"] == "message not found"
    assert _rows(alice) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"rating": 2},
        {"rating": 0},
        {"rating": "up"},
        {"report": {"reason": "boring"}},
        {"report": {"reason": "other", "comment": "x" * 1001}},
        {"rating": 1, "language": "xx"},
        {"rating": 1, "unexpected": True},
    ],
)
def test_invalid_payload_is_rejected(alice, payload):
    _, answer_id = _answer(alice)

    assert _put(alice, answer_id, payload).status_code == 422
    assert _rows(alice) == []


# --- oceny -------------------------------------------------------------------

def test_rating_stores_snapshot_of_question_answer_and_sources(alice, fake_sources):
    _, answer_id = _answer(alice, "Kiedy sesja?")

    r = _put(alice, answer_id, {"rating": 1, "language": "en"})

    assert r.status_code == 200, r.text
    assert r.json() == {"rating": 1, "reported": False}
    (row,) = _rows(alice)
    assert row.message_id == answer_id
    assert row.rating == 1
    assert row.question == "Kiedy sesja?"
    assert row.answer == "odpowiedz na: Kiedy sesja?"
    assert row.sources == fake_sources
    assert row.language == "en"
    assert row.report_reason is None and row.report_status is None


def test_snapshot_takes_the_question_right_before_the_answer(alice):
    conversation_id, _ = _answer(alice, "pierwsze")
    second = _ask(alice, "drugie", conversation_id)["message"]["id"]

    _put(alice, second, {"rating": -1})

    (row,) = _rows(alice)
    assert row.question == "drugie"


def test_changing_rating_updates_the_same_row(alice):
    _, answer_id = _answer(alice)

    _put(alice, answer_id, {"rating": 1})
    r = _put(alice, answer_id, {"rating": -1})

    assert r.json() == {"rating": -1, "reported": False}
    (row,) = _rows(alice)
    assert row.rating == -1


def test_clearing_rating_removes_row_without_report(alice):
    _, answer_id = _answer(alice)
    _put(alice, answer_id, {"rating": 1})

    r = _put(alice, answer_id, {"rating": None})

    assert r.status_code == 200
    assert r.json() == {"rating": None, "reported": False}
    assert _rows(alice) == []


# --- zgloszenia ----------------------------------------------------------------

def test_report_keeps_rating_and_trims_comment(alice):
    _, answer_id = _answer(alice)
    _put(alice, answer_id, {"rating": -1})

    r = _put(alice, answer_id, {"report": {"reason": "outdated", "comment": "  stary termin  "}})

    assert r.json() == {"rating": -1, "reported": True}
    (row,) = _rows(alice)
    assert row.rating == -1
    assert row.report_reason == "outdated"
    assert row.comment == "stary termin"
    assert row.report_status == "open"
    assert row.reported_at is not None


def test_blank_comment_is_stored_as_none(alice):
    _, answer_id = _answer(alice)

    _put(alice, answer_id, {"report": {"reason": "wrong", "comment": "   "}})

    (row,) = _rows(alice)
    assert row.comment is None
    assert row.rating is None


def test_clearing_rating_keeps_the_report(alice):
    _, answer_id = _answer(alice)
    _put(alice, answer_id, {"rating": -1, "report": {"reason": "inappropriate"}})

    r = _put(alice, answer_id, {"rating": None})

    assert r.json() == {"rating": None, "reported": True}
    (row,) = _rows(alice)
    assert row.rating is None and row.report_reason == "inappropriate"


def test_second_report_replaces_the_first_and_reopens_it(alice):
    _, answer_id = _answer(alice)
    _put(alice, answer_id, {"report": {"reason": "wrong", "comment": "a"}})
    db = alice.session_factory()
    row = db.execute(select(MessageFeedback)).scalar_one()
    row.report_status = "resolved"
    row.admin_note = "poprawione"
    db.commit()
    db.close()

    _put(alice, answer_id, {"report": {"reason": "other", "comment": "b"}})

    (row,) = _rows(alice)
    assert (row.report_reason, row.comment, row.report_status, row.admin_note) == ("other", "b", "open", None)


def test_one_row_per_user_and_message(alice):
    _, answer_id = _answer(alice)

    for payload in ({"rating": 1}, {"rating": -1}, {"report": {"reason": "other"}}, {"rating": 1}):
        assert _put(alice, answer_id, payload).status_code == 200

    assert len(_rows(alice)) == 1


# --- stan po przeladowaniu ----------------------------------------------------

def test_conversation_messages_carry_the_users_feedback(alice):
    conversation_id, first = _answer(alice, "pierwsze")
    second = _ask(alice, "drugie", conversation_id)["message"]["id"]
    _put(alice, first, {"rating": 1})
    _put(alice, second, {"report": {"reason": "wrong"}})

    messages = alice.get(f"/conversations/{conversation_id}").json()["messages"]

    by_id = {m["id"]: m for m in messages}
    assert by_id[first]["feedback"] == {"rating": 1, "reported": False}
    assert by_id[second]["feedback"] == {"rating": None, "reported": True}
    assert all(m["feedback"] is None for m in messages if m["role"] == "user")


def test_answer_without_feedback_has_empty_state(alice):
    conversation_id, answer_id = _answer(alice)

    (_, answer) = alice.get(f"/conversations/{conversation_id}").json()["messages"]

    assert answer["id"] == answer_id
    assert answer["feedback"] == {"rating": None, "reported": False}


# --- kopia przezywa usuniecie rozmowy -----------------------------------------

def test_feedback_survives_deleting_the_conversation(alice):
    conversation_id, answer_id = _answer(alice)
    _put(alice, answer_id, {"rating": -1, "report": {"reason": "wrong"}})

    assert alice.delete(f"/conversations/{conversation_id}").status_code == 204

    (row,) = _rows(alice)
    assert row.message_id is None
    assert row.answer == "odpowiedz na: Kiedy sesja?"
    assert row.report_status == "open"


def test_feedback_survives_purging_expired_conversations(alice):
    conversation_id, answer_id = _answer(alice)
    _put(alice, answer_id, {"rating": 1})
    db = alice.session_factory()
    conversation = db.get(Conversation, conversation_id)
    conversation.last_message_at = datetime.now(timezone.utc) - timedelta(days=40)
    db.commit()

    assert purge_expired_conversations(db, retention_days=30) == 1
    db.close()

    (row,) = _rows(alice)
    assert row.message_id is None and row.rating == 1


def test_feedback_survives_regenerating_the_answer(alice):
    conversation_id, answer_id = _answer(alice)
    _put(alice, answer_id, {"rating": -1})

    new_answer = _ask(alice, "Kiedy sesja?", conversation_id, regenerate=True)["message"]

    (row,) = _rows(alice)
    assert row.message_id is None and row.rating == -1
    messages = alice.get(f"/conversations/{conversation_id}").json()["messages"]
    assert messages[-1]["id"] == new_answer["id"]
    assert messages[-1]["feedback"] == {"rating": None, "reported": False}
