"""
Testy POST /chat/stream (odpowiedz strumieniowana jako SSE), jezyka odpowiedzi
i zrodel w odpowiedziach API. Warstwa LLM to atrapa z conftest.py.
"""

import json

import pytest

from src.backend import main as main_module
from src.backend.database import get_messages
from src.backend.llm.generate import AnswerStream
from src.backend.models import Conversation, Message, MessageRole, User

OTHER_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def member(client, member_override):
    return client


def _parse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        fields = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def _stream(client, body: dict, **kwargs):
    with client.stream("POST", "/chat/stream", json=body, **kwargs) as response:
        response.read()
        return response


def _messages(client, conversation_id):
    db = client.session_factory()
    try:
        return [(m.role, m.content) for m in get_messages(db, conversation_id)]
    finally:
        db.close()


def test_stream_sends_deltas_then_done_and_saves_answer(member, fake_sources):
    response = _stream(member, {"message": "kim jest Jan Kowalski"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["cache-control"] == "no-cache"
    events = _parse_events(response.text)
    assert [name for name, _ in events] == ["delta", "delta", "delta", "done"]
    text = "".join(data["text"] for name, data in events if name == "delta")
    assert text == "odpowiedz na: kim jest Jan Kowalski"

    done = events[-1][1]
    cid = done["conversation_id"]
    assert done["message"]["role"] == "assistant"
    assert done["message"]["content"] == text
    assert done["message"]["sources"] == fake_sources
    assert _messages(member, cid) == [
        (MessageRole.USER, "kim jest Jan Kowalski"),
        (MessageRole.ASSISTANT, text),
    ]
    stored = member.get(f"/conversations/{cid}").json()["messages"]
    assert stored[1]["sources"] == fake_sources


def test_stream_followup_passes_history_and_language(member):
    first = _parse_events(_stream(member, {"message": "kim jest Jan Kowalski"}).text)
    cid = first[-1][1]["conversation_id"]

    _stream(member, {"message": "a jakie ma dyzury?", "conversation_id": cid, "language": "en"})

    assert member.calls[-1]["language"] == "en"
    assert [m["role"] for m in member.calls[-1]["history"]] == ["user", "assistant"]
    assert len(_messages(member, cid)) == 4


def test_stream_regenerate_replaces_previous_answer(member):
    cid = _parse_events(_stream(member, {"message": "pytanie"}).text)[-1][1]["conversation_id"]

    _stream(member, {"message": "pytanie", "conversation_id": cid, "regenerate": True})

    assert member.calls[-1]["history"] == []
    assert _messages(member, cid) == [
        (MessageRole.USER, "pytanie"),
        (MessageRole.ASSISTANT, "odpowiedz na: pytanie"),
    ]
    assert member.get("/stats").json()["total_prompts"] == 1


def test_stream_llm_failure_sends_error_and_saves_nothing(member, monkeypatch):
    def broken(message, history=None, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(main_module, "rag_stream", broken)

    response = _stream(member, {"message": "nie zadziala", "conversation_id": OTHER_ID})

    assert response.status_code == 200
    events = _parse_events(response.text)
    assert len(events) == 1
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "llm_failed"
    assert events[0][1]["message"]
    assert "LLM down" not in events[0][1]["message"]
    assert member.get(f"/conversations/{OTHER_ID}").status_code == 404


def test_stream_failure_midway_keeps_conversation_unchanged(member, monkeypatch):
    cid = _parse_events(_stream(member, {"message": "pytanie"}).text)[-1][1]["conversation_id"]
    before = _messages(member, cid)

    def failing_chunks():
        yield "poczatek "
        raise RuntimeError("zerwane polaczenie")

    monkeypatch.setattr(
        main_module,
        "rag_stream",
        lambda message, history=None, **kwargs: AnswerStream(chunks=failing_chunks(), files=[], sources=[]),
    )

    events = _parse_events(
        _stream(member, {"message": "pytanie", "conversation_id": cid, "regenerate": True}).text
    )

    assert [name for name, _ in events] == ["delta", "error"]
    assert _messages(member, cid) == before


def test_stream_requires_login(client):
    response = _stream(client, {"message": "hej"})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")


def test_stream_rejects_foreign_origin(member):
    response = _stream(member, {"message": "hej"}, headers={"Origin": "https://evil.ksi.sh"})

    assert response.status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "hej", "language": "ru"},
        {"message": "hej", "conversation_id": "nie-hex"},
    ],
)
def test_stream_validates_body(member, body):
    assert _stream(member, body).status_code == 422


def test_stream_into_someone_elses_conversation_is_404(member):
    db = member.session_factory()
    other = User(oidc_sub="someone-else")
    db.add(other)
    db.commit()
    db.add(Conversation(id=OTHER_ID, user_id=other.id))
    db.commit()
    db.close()

    response = _stream(member, {"message": "przejmuje", "conversation_id": OTHER_ID})

    assert response.status_code == 404
    assert _messages(member, OTHER_ID) == []


# --- /chat (JSON) --------------------------------------------------------------

def test_chat_passes_language_and_returns_sources(member, fake_sources):
    r = member.post("/chat", json={"message": "kim jest Jan Kowalski", "language": "fr"})

    assert r.status_code == 200
    assert member.calls[-1]["language"] == "fr"
    assert r.json()["message"]["sources"] == fake_sources


def test_chat_defaults_to_polish(member):
    member.post("/chat", json={"message": "kim jest Jan Kowalski"})

    assert member.calls[-1]["language"] == "pl"


def test_chat_rejects_unknown_language(member):
    assert member.post("/chat", json={"message": "hej", "language": "ru"}).status_code == 422


def test_legacy_and_invalid_sources_are_skipped_in_responses(member):
    cid = member.post("/chat", json={"message": "pytanie"}).json()["conversation_id"]
    db = member.session_factory()
    answer = db.query(Message).filter_by(conversation_id=cid, role=MessageRole.ASSISTANT).one()
    answer.sources = [
        "data/mordor/mapy/plan.png",
        {"kind": "usos", "title": "Jan Kowalski", "url": "https://usosweb.uj.edu.pl/jk"},
        {"kind": "nieznane", "title": "x", "url": None},
        {"kind": "mordor"},
    ]
    db.commit()
    db.close()

    messages = member.get(f"/conversations/{cid}").json()["messages"]

    assert messages[1]["sources"] == [
        {"kind": "usos", "title": "Jan Kowalski", "url": "https://usosweb.uj.edu.pl/jk"}
    ]
