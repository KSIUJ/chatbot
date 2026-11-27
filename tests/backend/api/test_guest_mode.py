"""Wersja testowa bez konta (tryb goscia): POST /auth/guest zaklada konto
goscia z sesja bez Keycloaka, gosc ma GUEST_QUESTION_LIMIT pytan na cala
sesje, limity per adres IP i dzienny limit wszystkich gosci, a funkcje
wymagajace konta KSI (USOS, statystyki, panel) sa dla niego zamkniete."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.backend.guest.service import purge_expired_guests
from src.backend.guest.settings import get_guest_settings
from src.backend.models import Conversation, DailyUsage, Message, MessageFeedback, UsageCounter, User, UserSession

from fake_keycloak import login

GUEST_IP = "203.0.113.7"


def start_guest(client, ip: str = GUEST_IP, origin: str | None = None):
    headers = {"X-Client-IP": ip}
    if origin is not None:
        headers["Origin"] = origin
    return client.post("/auth/guest", headers=headers)


def ask(client, question: str = "Gdzie jest dziekanat?", conversation_id: str | None = None):
    payload: dict[str, object] = {"message": question}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    return client.post("/chat", json=payload)


@pytest.fixture
def guest_env(monkeypatch: pytest.MonkeyPatch):
    """Ustawia zmienne GUEST_* i czysci cache ustawien gosci."""

    def apply(**values: str) -> None:
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        get_guest_settings.cache_clear()

    yield apply
    get_guest_settings.cache_clear()


# --- start sesji goscia ----------------------------------------------------------

def test_guest_mode_info_is_public(client):
    response = client.get("/auth/guest")

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "question_limit": 2}


def test_start_guest_sets_session_without_keycloak(client):
    response = start_guest(client)

    assert response.status_code == 200
    me = client.get("/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["is_guest"] is True
    assert body["is_admin"] is False
    assert body["email"] is None
    # ani przy starcie, ani przy /auth/me nikt nie pyta Keycloaka
    assert client.keycloak.calls == []


def test_start_guest_rejects_foreign_origin(client):
    response = start_guest(client, origin="https://evil.example")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden_origin"


def test_start_guest_twice_keeps_the_same_guest(client):
    start_guest(client)
    first = client.get("/auth/me").json()["id"]

    start_guest(client)

    assert client.get("/auth/me").json()["id"] == first
    db = client.session_factory()
    guests = db.scalars(select(User.id).where(User.is_guest.is_(True))).all()
    db.close()
    assert guests == [first]


def test_per_ip_limit_of_guest_sessions(client, guest_env):
    guest_env(GUEST_SESSIONS_PER_IP_PER_DAY="2")

    for _ in range(2):
        assert start_guest(client).status_code == 200
        client.cookies.clear()
    refused = start_guest(client)
    other_ip = start_guest(client, ip="198.51.100.9")

    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "guest_quota"
    assert other_ip.status_code == 200


def test_logout_does_not_reset_the_per_ip_limit(client, guest_env):
    guest_env(GUEST_SESSIONS_PER_IP_PER_DAY="2")

    for _ in range(2):
        assert start_guest(client).status_code == 200
        assert client.post("/auth/logout").status_code == 200
    refused = start_guest(client)

    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "guest_quota"


def test_ipv6_addresses_of_one_network_share_the_limit(client, guest_env):
    guest_env(GUEST_SESSIONS_PER_IP_PER_DAY="1")

    assert start_guest(client, ip="2001:db8:1:2::10").status_code == 200
    client.cookies.clear()
    refused = start_guest(client, ip="2001:db8:1:2:ffff::99")
    other_network = start_guest(client, ip="2001:db8:1:3::10")

    assert refused.status_code == 429
    assert other_network.status_code == 200


def test_invalid_client_address_is_rejected(client):
    response = start_guest(client, ip="not-an-ip")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "bad_client_address"


def test_guest_ip_is_never_stored(client):
    start_guest(client)

    db = client.session_factory()
    keys = db.scalars(select(UsageCounter.key)).all()
    guest = db.scalar(select(User).where(User.is_guest.is_(True)))
    db.close()
    assert guest is not None
    assert keys and all(GUEST_IP not in key for key in keys)
    assert GUEST_IP not in " ".join(str(v) for v in vars(guest).values())


def test_guest_mode_off(client, guest_env):
    start_guest(client)
    guest_env(GUEST_MODE="off")

    assert client.get("/auth/guest").json()["enabled"] is False
    # istniejaca sesja goscia przestaje dzialac
    assert client.get("/auth/me").status_code == 401
    client.cookies.clear()
    refused = start_guest(client)
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "guest_disabled"


# --- limit pytan -------------------------------------------------------------------

def test_guest_gets_two_questions_then_429(client):
    start_guest(client)

    first = ask(client)
    second = ask(client, "A godziny otwarcia?", first.json()["conversation_id"])
    third = ask(client, "I jeszcze jedno")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "guest_limit_reached"
    assert third.json()["detail"]["limit"] == 2
    assert len(client.calls) == 2


def test_guest_limit_does_not_reset_at_midnight(client):
    start_guest(client)
    ask(client)
    ask(client)

    db = client.session_factory()
    guest = db.scalar(select(User).where(User.is_guest.is_(True)))
    rows = db.scalars(select(DailyUsage).where(DailyUsage.user_id == guest.id)).all()
    db.close()
    # oba pytania na jednym liczniku - dniu utworzenia goscia
    assert [row.count for row in rows] == [2]


def test_stream_counts_against_the_guest_limit(client):
    start_guest(client)

    for _ in range(2):
        response = client.post("/chat/stream", json={"message": "Pytanie"})
        assert response.status_code == 200
    third = client.post("/chat/stream", json={"message": "Pytanie"})

    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "guest_limit_reached"


def test_usage_reports_the_guest_limit(client):
    start_guest(client)
    ask(client)

    usage = client.get("/usage").json()

    assert usage["guest"] is True
    assert usage["used"] == 1
    assert usage["limit"] == 2


def test_member_usage_is_not_guest(client):
    login(client, client.keycloak)

    assert client.get("/usage").json()["guest"] is False


def test_daily_cap_of_all_guest_questions(client, guest_env):
    guest_env(GUEST_DAILY_TOTAL_LIMIT="1")
    start_guest(client)
    assert ask(client).status_code == 200
    client.cookies.clear()
    start_guest(client, ip="198.51.100.9")

    refused = ask(client)

    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "guest_capacity"
    assert len(client.calls) == 1


def test_member_questions_do_not_use_the_guest_cap(client, guest_env):
    guest_env(GUEST_DAILY_TOTAL_LIMIT="1")
    login(client, client.keycloak)

    assert ask(client).status_code == 200
    assert ask(client).status_code == 200


def test_failed_answer_keeps_the_daily_cap_of_all_guests(client, monkeypatch, guest_env):
    from src.backend import main as main_module

    guest_env(GUEST_DAILY_TOTAL_LIMIT="1")
    start_guest(client)

    def broken(*_args, **_kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(main_module, "rag_answer", broken)
    with pytest.raises(RuntimeError):
        ask(client)

    # pytanie wraca do goscia, ale nie do wspolnej puli - nieudane wywolania
    # modelu tez kosztuja
    assert client.get("/usage").json()["used"] == 0
    refused = ask(client)
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "guest_capacity"
    assert client.get("/usage").json()["guest_capacity_reached"] is True


def test_failed_answer_returns_the_guest_question(client, monkeypatch):
    from src.backend import main as main_module

    start_guest(client)

    def broken(*_args, **_kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(main_module, "rag_answer", broken)
    with pytest.raises(RuntimeError):
        ask(client)

    assert client.get("/usage").json()["used"] == 0


# --- co gosc moze, a czego nie ------------------------------------------------------

def test_guest_sees_only_own_conversations(client):
    start_guest(client)
    conversation_id = ask(client).json()["conversation_id"]

    listed = client.get("/conversations").json()["conversations"]

    assert [c["id"] for c in listed] == [conversation_id]
    assert client.get(f"/conversations/{conversation_id}").status_code == 200


@pytest.mark.parametrize("path", ["/usos/status", "/stats"])
def test_guest_cannot_use_member_only_endpoints(client, path):
    start_guest(client)

    response = client.get(path)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "guest_not_allowed"


def test_guest_is_not_admin(client):
    start_guest(client)

    response = client.get("/admin/feedback")

    assert response.status_code == 403


def test_stats_do_not_count_guests(client):
    start_guest(client)
    client.cookies.clear()
    login(client, client.keycloak)

    assert client.get("/stats").json()["accounts_created"] == 1


def test_guest_can_rate_an_answer(client):
    start_guest(client)
    message_id = ask(client).json()["message"]["id"]

    response = client.put(f"/messages/{message_id}/feedback", json={"rating": 1})

    assert response.status_code == 200


# --- zalaczniki ---------------------------------------------------------------------

def _upload_txt(client):
    return client.post(
        "/attachments",
        content=b"Notatka do pytania",
        headers={"X-Filename": "notatka.txt", "Content-Type": "application/octet-stream"},
    )


def test_guest_attachment_limit(client, guest_env):
    guest_env(GUEST_ATTACHMENT_LIMIT="1")
    start_guest(client)

    assert _upload_txt(client).status_code == 201
    refused = _upload_txt(client)

    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "attachments_limited"


def test_guest_files_have_a_smaller_size_limit(client):
    start_guest(client)

    too_big = client.post(
        "/attachments",
        content=b"a" * (5 * 1024 * 1024 + 1),
        headers={"X-Filename": "duzy.txt", "Content-Type": "application/octet-stream"},
    )

    assert too_big.status_code == 413
    assert client.get("/usage").json()["attachments"]["max_file_mb"] == 5


def test_guest_without_questions_cannot_upload(client):
    start_guest(client)
    ask(client)
    ask(client)

    refused = _upload_txt(client)

    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "guest_limit_reached"


# --- koniec sesji i sprzatanie -------------------------------------------------------

def test_guest_logout_deletes_the_guest(client):
    start_guest(client)
    ask(client)

    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json()["logout_url"] is None
    db = client.session_factory()
    assert db.scalar(select(User).where(User.is_guest.is_(True))) is None
    assert db.scalar(select(Conversation)) is None
    assert db.scalar(select(UserSession)) is None
    db.close()


def test_purge_removes_expired_guests_only(client):
    start_guest(client)
    ask(client)
    client.cookies.clear()
    login(client, client.keycloak)
    ask(client)

    db = client.session_factory()
    later = datetime.now(timezone.utc) + timedelta(hours=25)
    removed = purge_expired_guests(db, now=later)
    users = db.scalars(select(User)).all()
    conversations = db.scalars(select(Conversation)).all()
    db.close()

    assert removed == 1
    assert [u.is_guest for u in users] == [False]
    assert len(conversations) == 1


def test_deleting_a_guest_drops_ratings_but_keeps_reports(client):
    start_guest(client)
    rated = ask(client).json()["message"]["id"]
    reported = ask(client, "Drugie").json()["message"]["id"]
    client.put(f"/messages/{rated}/feedback", json={"rating": 1})
    assert client.put(f"/messages/{reported}/feedback", json={"report": {"reason": "wrong", "comment": "zle"}}).status_code == 200

    client.post("/auth/logout")

    db = client.session_factory()
    rows = db.scalars(select(MessageFeedback)).all()
    db.close()
    assert [(row.rating, row.report_reason, row.user_id) for row in rows] == [(None, "wrong", None)]


def test_purge_removes_conversations_left_by_a_deleted_guest(client):
    start_guest(client)
    db = client.session_factory()
    guest_id = db.scalar(select(User.id).where(User.is_guest.is_(True)))
    # odpowiedz w toku zapisala rozmowe juz po skasowaniu goscia
    orphan = Conversation(user_id="0" * 32)
    db.add(orphan)
    db.commit()
    orphan_id = orphan.id
    db.add(Message(conversation_id=orphan_id, role="user", content="pytanie"))
    db.commit()

    purge_expired_guests(db, now=datetime.now(timezone.utc))

    assert db.get(Conversation, orphan_id) is None
    assert db.get(User, guest_id) is not None
    db.close()


def test_purge_keeps_fresh_guests(client):
    start_guest(client)

    db = client.session_factory()
    removed = purge_expired_guests(db, now=datetime.now(timezone.utc) + timedelta(hours=1))
    db.close()

    assert removed == 0
