"""
Testy zapisu odpowiedzi (takze czesciowej - po Stop albo zerwaniu polaczenia)
i generatora zdarzen SSE bez warstwy HTTP.
"""

import json
import threading

import anyio
import pytest

from src.backend.chat import ChatTurn, save_partial_answer
from src.backend.chat_stream import chat_events
from src.backend.database import add_message, create_conversation, get_messages
from src.backend.history import conversation_lock
from src.backend.llm.generate import AnswerStream
from src.backend.models import Conversation, MessageRole, User

CID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SOURCES = [{"kind": "usos", "title": "Jan Kowalski", "url": "https://usosweb.uj.edu.pl/jk"}]


@pytest.fixture
def user_id(session_factory) -> str:
    db = session_factory()
    user = User(oidc_sub="member")
    db.add(user)
    db.commit()
    uid = user.id
    db.close()
    return uid


def _turn(user_id: str, *, question: str = "pytanie", regenerate: bool = False, max_per_user: int = 10,
          conversation_id: str = CID) -> ChatTurn:
    return ChatTurn(
        user_id=user_id,
        conversation_id=conversation_id,
        question=question,
        regenerate=regenerate,
        language="pl",
        max_per_user=max_per_user,
    )


def _messages(session_factory, conversation_id: str = CID):
    db = session_factory()
    try:
        return [(m.role, m.content, m.sources) for m in get_messages(db, conversation_id)]
    finally:
        db.close()


def _seed_exchange(session_factory, user_id: str, conversation_id: str = CID) -> None:
    db = session_factory()
    create_conversation(db, user_id=user_id, conversation_id=conversation_id)
    add_message(db, conversation_id, MessageRole.USER, "pytanie")
    add_message(db, conversation_id, MessageRole.ASSISTANT, "stara odpowiedz")
    db.close()


# --- save_partial_answer -------------------------------------------------------

def test_partial_answer_starts_new_conversation(session_factory, user_id):
    saved = save_partial_answer(session_factory, _turn(user_id), "Dziekanat jest czyn", SOURCES)

    assert saved is not None
    assert saved.content == "Dziekanat jest czyn"
    assert [s.model_dump() for s in saved.sources] == SOURCES
    assert _messages(session_factory) == [
        (MessageRole.USER, "pytanie", []),
        (MessageRole.ASSISTANT, "Dziekanat jest czyn", SOURCES),
    ]


def test_partial_answer_in_new_conversation_makes_room(session_factory, user_id):
    old_id = "b" * 32
    _seed_exchange(session_factory, user_id, old_id)

    save_partial_answer(session_factory, _turn(user_id, max_per_user=1), "czesc", SOURCES)

    db = session_factory()
    try:
        assert db.get(Conversation, old_id) is None
        assert db.get(Conversation, CID) is not None
    finally:
        db.close()


def test_partial_answer_appends_to_followup(session_factory, user_id):
    _seed_exchange(session_factory, user_id)

    save_partial_answer(session_factory, _turn(user_id, question="a dyzury?"), "Dyzury sa w", [])

    assert [m[1] for m in _messages(session_factory)] == ["pytanie", "stara odpowiedz", "a dyzury?", "Dyzury sa w"]


def test_partial_answer_replaces_regenerated_answer(session_factory, user_id):
    _seed_exchange(session_factory, user_id)

    save_partial_answer(session_factory, _turn(user_id, regenerate=True), "nowa czesc", SOURCES)

    assert [m[1] for m in _messages(session_factory)] == ["pytanie", "nowa czesc"]


@pytest.mark.parametrize("text", ["", "   \n"])
def test_empty_partial_answer_saves_nothing(session_factory, user_id, text):
    _seed_exchange(session_factory, user_id)

    assert save_partial_answer(session_factory, _turn(user_id, regenerate=True), text, SOURCES) is None
    assert save_partial_answer(session_factory, _turn(user_id, conversation_id="c" * 32), text, []) is None

    assert [m[1] for m in _messages(session_factory)] == ["pytanie", "stara odpowiedz"]
    assert _messages(session_factory, "c" * 32) == []


# --- chat_events (bez HTTP) ----------------------------------------------------

class FakeProbe:
    """Atrapa Request.is_disconnected: klient znika po `after` sprawdzeniach."""

    def __init__(self, after: int | None = None):
        self.after = after
        self.checks = 0

    async def is_disconnected(self) -> bool:
        self.checks += 1
        return self.after is not None and self.checks >= self.after


class TrackedChunks:
    """Generator kawalkow, ktory zapamietuje, czy zostal zamkniety."""

    def __init__(self, chunks, gate: threading.Event | None = None):
        self.chunks = chunks
        self.gate = gate
        self.closed = False
        self.iterator = self._run()

    def _run(self):
        try:
            for index, chunk in enumerate(self.chunks):
                if index > 0 and self.gate is not None:
                    self.gate.wait(timeout=5)
                yield chunk
        finally:
            self.closed = True


def _stream_fn(tracked: TrackedChunks):
    def stream(message, history=None, language="pl", **kwargs):
        return AnswerStream(chunks=tracked.iterator, files=[], sources=list(SOURCES))

    return stream


def _decode(event: str) -> tuple[str, dict]:
    name_line, data_line = event.strip().split("\n")
    return name_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))


def test_events_end_with_done_and_full_answer(session_factory, user_id):
    tracked = TrackedChunks(["Dzie", "kanat"])

    async def run():
        return [_decode(e) async for e in chat_events(FakeProbe(), session_factory, _turn(user_id),
                                                       _stream_fn(tracked))]

    events = anyio.run(run)

    assert [name for name, _ in events] == ["delta", "delta", "done"]
    assert events[-1][1]["conversation_id"] == CID
    assert events[-1][1]["message"]["content"] == "Dziekanat"
    assert tracked.closed
    assert not conversation_lock(CID).locked()


def test_disconnect_saves_partial_answer_and_closes_upstream(session_factory, user_id):
    tracked = TrackedChunks(["Dzie", "kanat", " czynny"])

    async def run():
        # 1. sprawdzenie przed wywolaniem modelu, 2. po pierwszym kawalku
        return [_decode(e) async for e in chat_events(FakeProbe(after=2), session_factory, _turn(user_id),
                                                       _stream_fn(tracked))]

    events = anyio.run(run)

    assert [name for name, _ in events] == ["delta"]
    assert tracked.closed
    assert _messages(session_factory) == [
        (MessageRole.USER, "pytanie", []),
        (MessageRole.ASSISTANT, "Dzie", SOURCES),
    ]
    assert not conversation_lock(CID).locked()


def test_closed_event_stream_saves_partial_answer(session_factory, user_id):
    tracked = TrackedChunks(["Dzie", "kanat"])

    async def run():
        events = chat_events(FakeProbe(), session_factory, _turn(user_id), _stream_fn(tracked))
        first = await events.__anext__()
        await events.aclose()
        return first

    first = anyio.run(run)

    assert _decode(first) == ("delta", {"text": "Dzie"})
    assert tracked.closed
    assert [m[1] for m in _messages(session_factory)] == ["pytanie", "Dzie"]
    assert not conversation_lock(CID).locked()


def test_cancelled_stream_saves_partial_answer(session_factory, user_id):
    gate = threading.Event()
    tracked = TrackedChunks(["Dzie", "kanat"], gate=gate)
    received = []

    async def run():
        with anyio.CancelScope() as scope:
            async for event in chat_events(FakeProbe(), session_factory, _turn(user_id), _stream_fn(tracked)):
                received.append(_decode(event))
                # Stop w przegladarce: anulowanie, gdy model liczy dalej
                scope.cancel()
                gate.set()

    anyio.run(run)

    assert received == [("delta", {"text": "Dzie"})]
    assert tracked.closed
    assert [m[1] for m in _messages(session_factory)] == ["pytanie", "Dzie"]
    assert not conversation_lock(CID).locked()


def test_client_gone_before_generation_saves_nothing(session_factory, user_id):
    tracked = TrackedChunks(["Dzie"])
    calls = []

    def stream(message, history=None, **kwargs):
        calls.append(message)
        return AnswerStream(chunks=tracked.iterator, files=[], sources=[])

    async def run():
        return [e async for e in chat_events(FakeProbe(after=1), session_factory, _turn(user_id), stream)]

    assert anyio.run(run) == []
    assert calls == []
    assert _messages(session_factory) == []
    assert not conversation_lock(CID).locked()


def test_empty_model_answer_is_an_error(session_factory, user_id):
    tracked = TrackedChunks(["", "  "])

    async def run():
        return [_decode(e) async for e in chat_events(FakeProbe(), session_factory, _turn(user_id),
                                                       _stream_fn(tracked))]

    events = anyio.run(run)

    assert [name for name, _ in events] == ["delta", "error"]
    assert events[-1][1]["code"] == "llm_failed"
    assert _messages(session_factory) == []


# --- blokada rozmowy -----------------------------------------------------------

def test_waiting_for_busy_conversation_does_not_hold_worker_thread(session_factory, user_id):
    tracked = TrackedChunks(["Dzie", "kanat"])
    lock = conversation_lock(CID)
    lock.acquire()
    snapshot = {}
    events = []

    async def run():
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = 1

        async def consume():
            async for event in chat_events(FakeProbe(), session_factory, _turn(user_id), _stream_fn(tracked)):
                events.append(_decode(event)[0])

        async with anyio.create_task_group() as tg:
            tg.start_soon(consume)
            await anyio.sleep(0.2)
            snapshot["borrowed"] = limiter.borrowed_tokens
            snapshot["events"] = list(events)
            lock.release()

    try:
        anyio.run(run)
    finally:
        if lock.locked() and snapshot.get("borrowed") is None:
            lock.release()

    assert snapshot == {"borrowed": 0, "events": []}
    assert events == ["delta", "delta", "done"]
    assert not lock.locked()


def test_cancel_while_waiting_for_lock_leaves_it_to_holder(session_factory, user_id):
    tracked = TrackedChunks(["Dzie"])
    lock = conversation_lock(CID)
    lock.acquire()

    async def run():
        with anyio.move_on_after(0.2):
            async for _ in chat_events(FakeProbe(), session_factory, _turn(user_id), _stream_fn(tracked)):
                pass

    try:
        anyio.run(run)
        assert lock.locked()
    finally:
        lock.release()
    assert not lock.locked()
    assert _messages(session_factory) == []


class _Boom(BaseException):
    pass


def test_lock_released_even_when_finish_raises(session_factory, user_id, monkeypatch):
    from src.backend import chat_stream

    async def broken_finish(*args):
        raise _Boom()

    monkeypatch.setattr(chat_stream, "_finish", broken_finish)
    tracked = TrackedChunks(["Dzie"])

    async def run():
        async for _ in chat_events(FakeProbe(), session_factory, _turn(user_id), _stream_fn(tracked)):
            pass

    with pytest.raises(_Boom):
        anyio.run(run)
    assert not conversation_lock(CID).locked()
