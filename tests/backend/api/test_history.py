"""
Historia rozmow: lista w sidebarze, usuwanie, limit rozmow na konto,
usuwanie nieuzywanych rozmow po CHAT_HISTORY_RETENTION_DAYS i statystyki,
ktore nie maleja po usunieciu rozmow.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.backend.history import (
    HistorySettings,
    get_history_settings,
    purge_expired_conversations,
    run_cleanup,
)
from src.backend.main import app, cleanup_jobs
from src.backend.models import Conversation, Message, User, UserSession

from fake_keycloak import login


def _conversations(client) -> list[Conversation]:
    db = client.session_factory()
    try:
        return list(db.execute(select(Conversation)).scalars())
    finally:
        db.close()


def _message_count(client) -> int:
    db = client.session_factory()
    try:
        return len(list(db.execute(select(Message)).scalars()))
    finally:
        db.close()


def _age_conversation(client, conversation_id: str, days: float) -> None:
    db = client.session_factory()
    try:
        conversation = db.get(Conversation, conversation_id)
        conversation.last_message_at = datetime.now(timezone.utc) - timedelta(days=days)
        db.commit()
    finally:
        db.close()


def _history(client) -> list[dict]:
    r = client.get("/conversations")
    assert r.status_code == 200, r.text
    return r.json()["conversations"]


def _ask(client, message: str, conversation_id: str | None = None) -> str:
    payload = {"message": message}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    r = client.post("/chat", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["conversation_id"]


@pytest.fixture
def small_history():
    """Limit 3 rozmow zamiast 10, zeby testy byly krotkie."""
    app.dependency_overrides[get_history_settings] = lambda: HistorySettings(
        max_per_user=3, retention_days=30, purge_interval_hours=6
    )
    yield
    app.dependency_overrides.pop(get_history_settings, None)


# --- lista -------------------------------------------------------------------

def test_history_requires_login(client):
    assert client.get("/conversations").status_code == 401
    assert client.delete("/conversations/abc").status_code == 401


def test_new_account_has_empty_history_and_sees_limits(client):
    login(client, client.keycloak, "alice")

    body = client.get("/conversations").json()

    assert body == {"conversations": [], "max_per_user": 10, "retention_days": 30}


def test_history_lists_own_conversations_newest_first_with_titles(client):
    login(client, client.keycloak, "alice")
    first = _ask(client, "Kiedy jest sesja zimowa?")
    second = _ask(client, "Kto prowadzi analizę?")

    history = _history(client)

    assert [c["id"] for c in history] == [second, first]
    assert [c["title"] for c in history] == ["Kto prowadzi analizę?", "Kiedy jest sesja zimowa?"]
    assert all(c["last_message_at"] for c in history)


def test_history_is_private(client):
    login(client, client.keycloak, "alice")
    _ask(client, "pytanie alicji")
    client.post("/auth/logout")

    login(client, client.keycloak, "bob")

    assert _history(client) == []


def test_title_is_first_question_shortened_to_one_line(client):
    login(client, client.keycloak, "alice")
    long_question = "Jakie   są\nzasady " + "bardzo " * 30 + "długiego pytania?"

    cid = _ask(client, long_question)
    _ask(client, "dopytanie, które nie zmienia tytułu", cid)

    (entry,) = _history(client)
    assert entry["title"].startswith("Jakie są zasady bardzo")
    assert "\n" not in entry["title"]
    assert len(entry["title"]) <= 80
    assert entry["title"].endswith("…")


def test_continuing_old_conversation_moves_it_to_top(client):
    login(client, client.keycloak, "alice")
    old = _ask(client, "stara rozmowa")
    new = _ask(client, "nowa rozmowa")

    _ask(client, "wracam do starej", old)

    assert [c["id"] for c in _history(client)] == [old, new]


# --- usuwanie ----------------------------------------------------------------

def test_delete_own_conversation_removes_it_with_messages(client):
    login(client, client.keycloak, "alice")
    cid = _ask(client, "do usunięcia")

    r = client.delete(f"/conversations/{cid}")

    assert r.status_code == 204
    assert _history(client) == []
    assert client.get(f"/conversations/{cid}").status_code == 404
    assert _message_count(client) == 0


def test_cannot_delete_someone_elses_conversation(client):
    login(client, client.keycloak, "alice")
    cid = _ask(client, "pytanie alicji")
    client.post("/auth/logout")
    login(client, client.keycloak, "bob")

    assert client.delete(f"/conversations/{cid}").status_code == 404
    assert client.delete("/conversations/does-not-exist").status_code == 404
    assert len(_conversations(client)) == 1


# --- limit rozmow na konto ------------------------------------------------------

def test_starting_chat_over_limit_deletes_oldest(client, small_history):
    login(client, client.keycloak, "alice")
    ids = [_ask(client, f"pytanie {i}") for i in range(4)]

    history = [c["id"] for c in _history(client)]

    assert history == [ids[3], ids[2], ids[1]]
    assert client.get(f"/conversations/{ids[0]}").status_code == 404
    assert _message_count(client) == 3 * 2  # pytanie + odpowiedz w kazdej


def test_limit_is_per_account(client, small_history):
    login(client, client.keycloak, "alice")
    alice_ids = [_ask(client, f"alicja {i}") for i in range(3)]
    client.post("/auth/logout")
    login(client, client.keycloak, "bob")

    _ask(client, "bob 0")

    client.post("/auth/logout")
    login(client, client.keycloak, "alice")
    assert {c["id"] for c in _history(client)} == set(alice_ids)


def test_continuing_existing_conversation_at_limit_deletes_nothing(client, small_history):
    login(client, client.keycloak, "alice")
    ids = [_ask(client, f"pytanie {i}") for i in range(3)]

    _ask(client, "dalej", ids[0])

    assert len(_history(client)) == 3


# --- usuwanie nieuzywanych rozmow ------------------------------------------------

def test_purge_deletes_conversations_unused_for_retention_period(client):
    login(client, client.keycloak, "alice")
    stale = _ask(client, "stara")
    fresh = _ask(client, "świeża")
    _age_conversation(client, stale, days=31)
    _age_conversation(client, fresh, days=29)

    db = client.session_factory()
    try:
        deleted = purge_expired_conversations(db, retention_days=30)
    finally:
        db.close()

    assert deleted == 1
    assert [c.id for c in _conversations(client)] == [fresh]
    assert _message_count(client) == 2


def test_purge_also_removes_old_anonymous_conversations(client):
    db = client.session_factory()
    try:
        anonymous = Conversation(user_id=None, last_message_at=datetime.now(timezone.utc) - timedelta(days=90))
        db.add(anonymous)
        db.commit()
        deleted = purge_expired_conversations(db, retention_days=30)
    finally:
        db.close()

    assert deleted == 1
    assert _conversations(client) == []


def test_purge_handles_backlog_larger_than_sqlite_parameter_limit(client):
    old = datetime.now(timezone.utc) - timedelta(days=60)
    db = client.session_factory()
    try:
        db.add_all([Conversation(user_id=None, last_message_at=old) for _ in range(1500)])
        db.commit()
        deleted = purge_expired_conversations(db, retention_days=30)
    finally:
        db.close()

    assert deleted == 1500
    assert _conversations(client) == []


# --- sprzatanie w tle: rozmowy i wygasle sesje ------------------------------------

def _add_session(db, user: User, session_id: str, expires_in: timedelta) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        UserSession(
            id=session_id,
            user_id=user.id,
            expires_at=now + expires_in,
            access_token_enc="x",
            access_token_expires_at=now,
        )
    )


def _session_ids(client) -> set[str]:
    db = client.session_factory()
    try:
        return set(db.execute(select(UserSession.id)).scalars())
    finally:
        db.close()


def test_cleanup_removes_expired_sessions_and_old_conversations(client):
    db = client.session_factory()
    try:
        user = User(oidc_sub="cleanup-user")
        db.add(user)
        db.flush()
        _add_session(db, user, "a" * 64, timedelta(hours=-1))
        _add_session(db, user, "b" * 64, timedelta(hours=1))
        db.add(Conversation(user_id=user.id, last_message_at=datetime.now(timezone.utc) - timedelta(days=31)))
        db.commit()
    finally:
        db.close()
    settings = HistorySettings(max_per_user=10, retention_days=30, purge_interval_hours=6)

    run_cleanup(client.session_factory, cleanup_jobs(settings))

    assert _session_ids(client) == {"b" * 64}
    assert _conversations(client) == []


def test_failing_cleanup_job_does_not_stop_the_others(client):
    db = client.session_factory()
    try:
        db.add(Conversation(user_id=None, last_message_at=datetime.now(timezone.utc) - timedelta(days=60)))
        db.commit()
    finally:
        db.close()

    def broken(_db) -> int:
        raise RuntimeError("boom")

    run_cleanup(
        client.session_factory,
        {"broken": broken, "conversations": lambda d: purge_expired_conversations(d, retention_days=30)},
    )

    assert _conversations(client) == []


# --- id nadawane przez klienta i awarie ------------------------------------------

NEW_ID = "0123456789abcdef0123456789abcdef"


def test_new_conversation_uses_client_generated_id(client):
    login(client, client.keycloak, "alice")

    cid = _ask(client, "pierwsze", NEW_ID)
    again = _ask(client, "drugie", NEW_ID)

    assert cid == again == NEW_ID
    (entry,) = _history(client)
    assert entry["id"] == NEW_ID and entry["title"] == "pierwsze"


@pytest.mark.parametrize("bad_id", ["short", "Z" * 32, "../../etc/passwd", "0123456789ABCDEF0123456789ABCDEF"])
def test_conversation_id_must_be_32_lowercase_hex(client, bad_id):
    login(client, client.keycloak, "alice")

    r = client.post("/chat", json={"message": "hej", "conversation_id": bad_id})

    assert r.status_code == 422


def test_client_id_of_someone_elses_conversation_is_rejected(client):
    login(client, client.keycloak, "alice")
    _ask(client, "pytanie alicji", NEW_ID)
    client.post("/auth/logout")
    login(client, client.keycloak, "bob")

    r = client.post("/chat", json={"message": "przejmuję", "conversation_id": NEW_ID})

    assert r.status_code == 404
    db = client.session_factory()
    try:
        assert len(db.get(Conversation, NEW_ID).messages) == 2
    finally:
        db.close()


def test_failed_first_answer_neither_evicts_nor_leaves_empty_conversation(client, small_history, monkeypatch):
    login(client, client.keycloak, "alice")
    ids = [_ask(client, f"pytanie {i}") for i in range(3)]

    from src.backend import main as main_module

    def broken_llm(message, history=None, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(main_module, "rag_answer", broken_llm)
    with pytest.raises(RuntimeError):
        client.post("/chat", json={"message": "nie zadziała", "conversation_id": NEW_ID})

    assert {c["id"] for c in _history(client)} == set(ids)
    assert client.get(f"/conversations/{NEW_ID}").status_code == 404


def test_message_length_is_limited(client):
    login(client, client.keycloak, "alice")

    r = client.post("/chat", json={"message": "x" * 4001})

    assert r.status_code == 422


# --- statystyki ---------------------------------------------------------------

def test_stats_do_not_shrink_when_conversations_are_deleted(client):
    login(client, client.keycloak, "alice")
    cid = _ask(client, "pierwsze")
    _ask(client, "drugie", cid)
    before = client.get("/stats").json()

    client.delete(f"/conversations/{cid}")

    after = client.get("/stats").json()
    assert before["total_prompts"] == 2
    assert after == before


def test_regenerate_does_not_count_as_new_prompt(client):
    login(client, client.keycloak, "alice")
    cid = _ask(client, "pytanie")

    client.post("/chat", json={"message": "pytanie", "conversation_id": cid, "regenerate": True})

    assert client.get("/stats").json()["total_prompts"] == 1
