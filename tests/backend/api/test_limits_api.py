"""
Dzienny limit pytan przez HTTP: 429 z kodem rate_limited, chwila odnowienia
i Retry-After dla POST /chat i /chat/stream (strumien nie startuje), zwrot
pytania po bledzie modelu, regeneracja liczy sie jak pytanie, GET /usage.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.backend import main as main_module
from src.backend.limits.settings import LimitSettings, load_default_limits, save_limit_settings
from src.backend.limits.usage import get_clock, set_user_limit

from fake_keycloak import login

# 20:00 UTC = 22:00 w Krakowie (CEST); polnoc za 2 godziny
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)
RESET_AT = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)
CID = "0123456789abcdef0123456789abcdef"


class Clock:
    """Zegar sterowany z testu."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    clock = Clock(NOW)
    main_module.app.dependency_overrides[get_clock] = lambda: clock
    return clock


@pytest.fixture
def member(client, member_override, clock):
    return client


def _set_global_limit(client, limit: int) -> None:
    db = client.session_factory()
    try:
        defaults = load_default_limits({})
        save_limit_settings(db, LimitSettings(daily_question_limit=limit, attachments=defaults.attachments), None)
    finally:
        db.close()


def _stream(client, body: dict):
    with client.stream("POST", "/chat/stream", json=body) as response:
        response.read()
        return response


def _assert_rate_limited(response, limit: int) -> None:
    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["retry-after"] == "7200"
    detail = response.json()["detail"]
    assert detail["code"] == "rate_limited"
    assert detail["limit"] == limit
    assert datetime.fromisoformat(detail["reset_at"]) == RESET_AT
    assert detail["message"]


def test_chat_over_the_limit_is_429_without_calling_the_model(member):
    _set_global_limit(member, 1)
    assert member.post("/chat", json={"message": "pierwsze"}).status_code == 200

    response = member.post("/chat", json={"message": "drugie"})

    _assert_rate_limited(response, 1)
    assert [call["message"] for call in member.calls] == ["pierwsze"]


def test_stream_over_the_limit_is_429_before_the_stream_starts(member):
    _set_global_limit(member, 1)
    assert _stream(member, {"message": "pierwsze"}).status_code == 200

    response = _stream(member, {"message": "drugie"})

    _assert_rate_limited(response, 1)
    assert "event:" not in response.text
    assert [call["message"] for call in member.calls] == ["pierwsze"]


def test_regenerate_counts_as_a_question(member):
    _set_global_limit(member, 2)
    cid = member.post("/chat", json={"message": "pytanie"}).json()["conversation_id"]
    member.post("/chat", json={"message": "pytanie", "conversation_id": cid, "regenerate": True})

    response = member.post("/chat", json={"message": "pytanie", "conversation_id": cid, "regenerate": True})

    assert response.status_code == 429


def test_failed_chat_is_refunded(member, monkeypatch):
    _set_global_limit(member, 1)

    def broken(message, history=None, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(main_module, "rag_answer", broken)
    with pytest.raises(RuntimeError):
        member.post("/chat", json={"message": "nie zadziala"})

    assert member.get("/usage").json()["used"] == 0


def test_failed_stream_is_refunded(member, monkeypatch):
    _set_global_limit(member, 1)

    def broken(message, history=None, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(main_module, "rag_stream", broken)
    events = _stream(member, {"message": "nie zadziala"}).text

    assert "llm_failed" in events
    assert member.get("/usage").json()["used"] == 0


def test_someone_elses_conversation_does_not_use_the_limit(member, client):
    _set_global_limit(member, 1)
    db = member.session_factory()
    try:
        from src.backend.models import Conversation, User

        other = User(oidc_sub="other")
        db.add(other)
        db.commit()
        db.add(Conversation(id=CID, user_id=other.id))
        db.commit()
    finally:
        db.close()

    assert member.post("/chat", json={"message": "x", "conversation_id": CID}).status_code == 404
    assert _stream(member, {"message": "x", "conversation_id": CID}).status_code == 404
    assert member.get("/usage").json()["used"] == 0


def test_limit_resets_at_warsaw_midnight(member, clock):
    _set_global_limit(member, 1)
    member.post("/chat", json={"message": "pierwsze"})
    assert member.post("/chat", json={"message": "drugie"}).status_code == 429

    clock.now = RESET_AT

    assert member.post("/chat", json={"message": "trzecie"}).status_code == 200


# --- GET /usage ---------------------------------------------------------------------------------

def test_usage_reports_used_limit_and_reset(member):
    _set_global_limit(member, 5)
    member.post("/chat", json={"message": "pierwsze"})
    _stream(member, {"message": "drugie"})

    response = member.get("/usage")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["used"] == 2
    assert body["limit"] == 5
    assert datetime.fromisoformat(body["reset_at"]) == RESET_AT


def test_usage_of_unlimited_user_has_null_limit(member, member_override):
    db = member.session_factory()
    try:
        set_user_limit(db, member_override, daily_limit=None, note=None, admin_id=None)
    finally:
        db.close()
    member.post("/chat", json={"message": "pierwsze"})

    body = member.get("/usage").json()

    assert body["used"] == 1
    assert body["limit"] is None


def test_usage_requires_login(client):
    response = client.get("/usage")

    assert response.status_code == 401


def test_usage_after_login(client, clock):
    login(client, client.keycloak, "alice")

    body = client.get("/usage").json()

    # conftest ustawia CHAT_DAILY_LIMIT=1000, zeby inne testy nie trafialy w limit
    assert (body["used"], body["limit"]) == (0, 1000)
    assert datetime.fromisoformat(body["reset_at"]) == RESET_AT


def test_failed_save_is_refunded_even_with_a_half_written_transaction(member, member_override, monkeypatch):
    _set_global_limit(member, 1)

    def broken_save(db, turn, answer_text, sources):
        from src.backend.models import Conversation

        # zapis przerwany w polowie: sesja zapytania trzyma blokade zapisu SQLite
        db.add(Conversation(id=turn.conversation_id, user_id=turn.user_id))
        db.flush()
        raise RuntimeError("disk full")

    monkeypatch.setattr(main_module, "save_exchange", broken_save)
    with pytest.raises(RuntimeError):
        member.post("/chat", json={"message": "pytanie", "conversation_id": CID})

    assert member.get("/usage").json()["used"] == 0
