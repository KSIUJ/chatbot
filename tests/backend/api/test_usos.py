"""
Polaczenie konta z USOS przeciw atrapie USOS API (fake_usos.FakeUsos, ktora
sprawdza podpisy OAuth 1.0a): /usos/connect -> zgoda w USOS -> /usos/callback,
ochrona przed CSRF (ciasteczko laczenia: brak, wygasle, podrobione, inny
request token, inne konto), odmowa, rozlaczenie z cofnieciem tokenu,
wiazanie szyfrogramu z kontem, brak tokenow w odpowiedziach i logach,
503 bez konfiguracji.
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import cryptography.fernet as fernet_module
import httpx
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from src.backend import main as main_module
from src.backend.auth.crypto import LoginState, TokenCipher
from src.backend.auth.settings import get_auth_settings
from src.backend.models import Base, User, UsosLink
from src.backend.usos.client import UsosClient, UsosUnauthorizedError
from src.backend.usos.crypto import UsosTokenCipher
from src.backend.usos.dependencies import get_usos_client
from src.backend.usos.service import get_user_token, mark_needs_reconnect, unlink, usos_user_call
from src.backend.usos.settings import get_usos_settings

from fake_keycloak import login
from fake_usos import CONSUMER_KEY, CONSUMER_SECRET, FakeUsos

USOS_COOKIE = "__Host-chatbot_usos"
SESSION_COOKIE = "__Host-chatbot_session"
ORIGIN = {"Origin": "https://chat.test"}


@pytest.fixture
def usos(client, monkeypatch: pytest.MonkeyPatch) -> FakeUsos:
    """Wlaczone laczenie z USOS, klient USOS API na atrapie."""
    monkeypatch.setenv("USOS_CONNECT", "on")
    monkeypatch.setenv("USOS_CONSUMER_KEY", CONSUMER_KEY)
    monkeypatch.setenv("USOS_CONSUMER_SECRET", CONSUMER_SECRET)
    get_usos_settings.cache_clear()
    fake = FakeUsos()
    usos_client = UsosClient(get_usos_settings(), httpx.Client(transport=httpx.MockTransport(fake.handler)))
    main_module.app.dependency_overrides[get_usos_client] = lambda: usos_client
    fake.client = usos_client
    return fake


def _query(response) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}


def _links(client) -> list[UsosLink]:
    db = client.session_factory()
    try:
        return list(db.execute(select(UsosLink)).scalars())
    finally:
        db.close()


def _user_id(client, sub: str) -> str:
    db = client.session_factory()
    try:
        return db.execute(select(User.id).where(User.oidc_sub == sub)).scalar_one()
    finally:
        db.close()


def _cipher() -> UsosTokenCipher:
    return UsosTokenCipher(get_auth_settings().secret_key)


def _start(client) -> str:
    r = client.post("/usos/connect", headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["authorize_url"]


def _connect(client, usos: FakeUsos, usos_id: str = "123"):
    token, verifier = usos.authorize(_start(client), usos_id)
    return client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)


# --- wylaczone / bez logowania ------------------------------------------

def test_disabled_without_configuration(client, keycloak):
    login(client, keycloak)

    status = client.get("/usos/status")
    assert status.status_code == 200
    assert status.json() == {
        "available": False, "connected": False, "needs_reconnect": False,
        "name": None, "connected_at": None, "scopes": [],
    }
    r = client.post("/usos/connect", headers=ORIGIN)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "usos_unavailable"
    back = client.get("/usos/callback", params={"oauth_token": "x", "oauth_verifier": "1"}, follow_redirects=False)
    assert back.status_code == 303
    assert _query(back) == {"usos_error": "unavailable"}


def test_key_alone_does_not_enable_connecting(client, keycloak, monkeypatch):
    # klucz aplikacji jest wspolny ze scraperem - wlacza dopiero USOS_CONNECT=on
    monkeypatch.setenv("USOS_CONSUMER_KEY", CONSUMER_KEY)
    monkeypatch.setenv("USOS_CONSUMER_SECRET", CONSUMER_SECRET)
    get_usos_settings.cache_clear()
    login(client, keycloak)

    assert client.get("/usos/status").json()["available"] is False
    assert client.post("/usos/connect", headers=ORIGIN).status_code == 503


def test_endpoints_require_login(client, usos):
    assert client.get("/usos/status").status_code == 401
    assert client.post("/usos/connect", headers=ORIGIN).status_code == 401
    assert client.delete("/usos/link", headers=ORIGIN).status_code == 401
    assert usos.calls == []


def test_callback_without_session_goes_back_with_error(client, keycloak, usos):
    login(client, keycloak)
    token, verifier = usos.authorize(_start(client))
    client.cookies.delete(SESSION_COOKIE)

    r = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)

    assert r.status_code == 303
    assert _query(r) == {"usos_error": "session"}
    assert "services/oauth/access_token" not in usos.calls
    assert _links(client) == []


def test_state_changing_endpoints_check_origin(client, keycloak, usos):
    login(client, keycloak)
    evil = {"Origin": "https://evil.example"}

    assert client.post("/usos/connect", headers=evil).status_code == 403
    assert client.delete("/usos/link", headers=evil).status_code == 403
    assert usos.calls == []


def test_connect_is_post_only(client, keycloak, usos):
    login(client, keycloak)

    assert client.get("/usos/connect").status_code == 405


# --- pelne polaczenie ----------------------------------------------------

def test_connect_and_callback_happy_path(client, keycloak, usos):
    login(client, keycloak)

    r = client.post("/usos/connect", headers=ORIGIN)

    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    authorize_url = r.json()["authorize_url"]
    assert authorize_url.startswith("https://apps.usos.uj.edu.pl/services/oauth/authorize?oauth_token=")
    [pending] = usos.request_tokens.values()
    assert pending.callback == "https://chat.test/api/usos/callback"
    assert pending.scopes == "studies|grades|crstests|student_exams|surveys_filling|payments|cards|events|adm_documents|placement_tests|offline_access"
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{USOS_COOKIE}=")
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=600"):
        assert flag in cookie
    # request token secret nie lezy w ciasteczku jawnie
    assert pending.secret not in cookie

    token, verifier = usos.authorize(authorize_url)
    back = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)

    assert back.status_code == 303
    assert back.headers["location"] == "/?usos=connected"
    assert f'{USOS_COOKIE}=""' in back.headers["set-cookie"]
    [link] = _links(client)
    access_token, access_secret = usos.last_access_token()
    assert link.user_id == _user_id(client, "alice")
    assert link.usos_user_id == "123"
    assert link.usos_name == "Jan Kowalski"
    assert link.scopes == "studies|grades|crstests|student_exams|surveys_filling|payments|cards|events|adm_documents|placement_tests|offline_access"
    assert access_token not in link.token_enc and access_secret not in link.token_enc
    assert usos.calls[-1] == "services/users/user"

    status = client.get("/usos/status")
    assert status.headers["cache-control"] == "no-store"
    body = status.json()
    assert body["available"] is True and body["connected"] is True and body["needs_reconnect"] is False
    assert body["name"] == "Jan Kowalski"
    assert body["connected_at"] is not None
    assert body["scopes"] == ["studies", "grades", "crstests", "student_exams", "surveys_filling", "payments", "cards",
                              "events", "adm_documents", "placement_tests", "offline_access"]
    for secret in (access_token, access_secret, link.token_enc):
        assert secret not in status.text


def test_connect_reports_usos_outage(client, keycloak, usos):
    login(client, keycloak)
    usos.fail["services/oauth/request_token"] = 503

    r = client.post("/usos/connect", headers=ORIGIN)

    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "usos_failed"
    assert USOS_COOKIE not in r.headers.get("set-cookie", "")


def test_callback_cookie_is_single_use(client, keycloak, usos):
    login(client, keycloak)
    token, verifier = usos.authorize(_start(client))
    params = {"oauth_token": token, "oauth_verifier": verifier}
    assert _query(client.get("/usos/callback", params=params, follow_redirects=False)) == {"usos": "connected"}

    again = client.get("/usos/callback", params=params, follow_redirects=False)

    assert _query(again) == {"usos_error": "expired"}


def test_reconnect_replaces_link_and_revokes_previous_token(client, keycloak, usos):
    login(client, keycloak)
    _connect(client, usos)
    first_token, _ = usos.last_access_token()

    r = _connect(client, usos)

    assert _query(r) == {"usos": "connected"}
    assert len(_links(client)) == 1
    assert usos.revoked == [first_token]


# --- CSRF i bledy przy powrocie ----------------------------------------------

def test_callback_without_cookie_is_rejected(client, keycloak, usos):
    login(client, keycloak)
    token, verifier = usos.authorize(_start(client))
    client.cookies.delete(USOS_COOKIE)

    r = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)

    assert _query(r) == {"usos_error": "expired"}
    assert "services/oauth/access_token" not in usos.calls
    assert _links(client) == []


def test_callback_with_expired_cookie_is_rejected(client, keycloak, usos, monkeypatch):
    login(client, keycloak)
    token, verifier = usos.authorize(_start(client))
    later = time.time() + 601
    monkeypatch.setattr(fernet_module, "time", SimpleNamespace(time=lambda: later))

    r = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)

    assert _query(r) == {"usos_error": "expired"}
    assert "services/oauth/access_token" not in usos.calls
    assert _links(client) == []


def test_callback_with_forged_cookie_is_rejected(client, keycloak, usos):
    login(client, keycloak)
    token, verifier = usos.authorize(_start(client))
    # ciasteczko logowania ma ten sam klucz, ale inny cel - nie przejdzie
    other_purpose = LoginState.generate().seal(TokenCipher(get_auth_settings().secret_key))
    for forged in ("garbage", other_purpose, TokenCipher("x" * 40).encrypt("{}")):
        client.cookies.set(USOS_COOKIE, forged, domain="chat.test", path="/")

        r = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)

        assert _query(r) == {"usos_error": "expired"}
    assert "services/oauth/access_token" not in usos.calls
    assert _links(client) == []


def test_callback_with_other_request_token_is_rejected(client, keycloak, usos):
    login(client, keycloak)
    _, verifier = usos.authorize(_start(client))

    for token in ("someoneElsesToken123", "", "żółć"):
        r = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)
        assert _query(r) == {"usos_error": "mismatch"}
        # mismatch zuzywa ciasteczko - nowe laczenie dla kolejnej proby
        _, verifier = usos.authorize(_start(client))
    assert "services/oauth/access_token" not in usos.calls
    assert _links(client) == []


def test_callback_in_session_of_another_account_is_rejected(client, keycloak, usos):
    login(client, keycloak, "alice")
    token, verifier = usos.authorize(_start(client))
    # w tej samej przegladarce ktos loguje sie innym kontem, ciasteczko alice zostaje
    login(client, keycloak, "bob")

    r = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)

    assert _query(r) == {"usos_error": "mismatch"}
    assert "services/oauth/access_token" not in usos.calls
    assert _links(client) == []


def test_denied_authorization(client, keycloak, usos):
    login(client, keycloak)
    token = parse_qs(urlsplit(_start(client)).query)["oauth_token"][0]

    r = client.get("/usos/callback", params={"oauth_token": token}, follow_redirects=False)

    assert _query(r) == {"usos_error": "denied"}
    assert f'{USOS_COOKIE}=""' in r.headers["set-cookie"]
    assert _links(client) == []


def test_wrong_verifier_counts_as_expired(client, keycloak, usos):
    login(client, keycloak)
    token, _ = usos.authorize(_start(client))

    r = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": "00000000"}, follow_redirects=False)

    assert _query(r) == {"usos_error": "expired"}
    assert _links(client) == []


def test_malformed_verifier_is_rejected_before_usos(client, keycloak, usos):
    login(client, keycloak)
    token, _ = usos.authorize(_start(client))

    r = client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": "12 34&x=1"}, follow_redirects=False)

    assert _query(r) == {"usos_error": "failed"}
    assert "services/oauth/access_token" not in usos.calls


def test_failed_identity_check_revokes_new_token(client, keycloak, usos):
    login(client, keycloak)
    usos.user_override = {"first_name": "bez id"}

    r = _connect(client, usos)

    assert _query(r) == {"usos_error": "failed"}
    assert _links(client) == []
    assert len(usos.revoked) == 1 and usos.access_tokens == {}


# --- rozlaczanie -------------------------------------------------------------

def test_disconnect_revokes_token_and_deletes_link(client, keycloak, usos):
    login(client, keycloak)
    _connect(client, usos)
    access_token, _ = usos.last_access_token()

    r = client.delete("/usos/link", headers=ORIGIN)

    assert r.status_code == 204
    assert usos.revoked == [access_token]
    assert _links(client) == []
    assert client.get("/usos/status").json()["connected"] is False
    # idempotentne
    assert client.delete("/usos/link", headers=ORIGIN).status_code == 204


def test_disconnect_deletes_link_even_when_revoke_fails(client, keycloak, usos, caplog):
    login(client, keycloak)
    _connect(client, usos)
    access_token, access_secret = usos.last_access_token()
    usos.fail["services/oauth/revoke_token"] = 500

    with caplog.at_level(logging.DEBUG):
        r = client.delete("/usos/link", headers=ORIGIN)

    assert r.status_code == 204
    assert _links(client) == []
    assert "cannot revoke usos token" in caplog.text
    assert access_token not in caplog.text and access_secret not in caplog.text


def test_disconnect_works_when_feature_is_switched_off(client, keycloak, usos, monkeypatch):
    login(client, keycloak)
    _connect(client, usos)
    monkeypatch.setenv("USOS_CONNECT", "off")
    get_usos_settings.cache_clear()

    status = client.get("/usos/status").json()
    assert status["available"] is False and status["connected"] is True

    assert client.delete("/usos/link", headers=ORIGIN).status_code == 204
    assert _links(client) == []


# --- tokeny: odczyt, 401, wiazanie z kontem ---------------------------------

def test_get_user_token_decrypts_and_marks_use(client, keycloak, usos):
    login(client, keycloak)
    _connect(client, usos)
    access_token, access_secret = usos.last_access_token()
    user_id = _user_id(client, "alice")
    db = client.session_factory()
    try:
        token = get_user_token(db, _cipher(), user_id)

        assert token is not None
        assert (token.user_id, token.token, token.secret) == (user_id, access_token, access_secret)
        assert access_token not in repr(token) and access_secret not in repr(token)
        assert db.get(UsosLink, user_id).last_used_at is not None
        assert usos_user_call(db, usos.client, token, "services/tt/user", start="2026-10-26") == {
            "ok": True, "params": {"start": "2026-10-26"},
        }
        assert get_user_token(db, _cipher(), "0" * 32) is None
    finally:
        db.close()


def test_rejected_token_needs_reconnect(client, keycloak, usos):
    login(client, keycloak)
    _connect(client, usos)
    user_id = _user_id(client, "alice")
    db = client.session_factory()
    try:
        token = get_user_token(db, _cipher(), user_id)
        # uzytkownik cofnal dostep w USOS
        usos.access_tokens.clear()

        with pytest.raises(UsosUnauthorizedError):
            usos_user_call(db, usos.client, token, "services/grades/terms2")

        assert get_user_token(db, _cipher(), user_id) is None
    finally:
        db.close()

    status = client.get("/usos/status").json()
    assert status["connected"] is False and status["needs_reconnect"] is True
    assert status["name"] == "Jan Kowalski"
    # ponowne polaczenie naprawia
    assert _query(_connect(client, usos)) == {"usos": "connected"}
    assert client.get("/usos/status").json()["connected"] is True


def test_ciphertext_moved_to_another_account_is_useless(client, keycloak, usos):
    login(client, keycloak, "alice")
    _connect(client, usos)
    login(client, keycloak, "bob")
    alice, bob = _user_id(client, "alice"), _user_id(client, "bob")
    db = client.session_factory()
    try:
        stolen = db.get(UsosLink, alice).token_enc
        db.add(UsosLink(user_id=bob, usos_user_id="123", usos_name="Jan Kowalski", token_enc=stolen, scopes="studies"))
        db.commit()

        assert get_user_token(db, _cipher(), bob) is None
        assert db.get(UsosLink, bob).needs_reconnect_at is not None
        assert get_user_token(db, _cipher(), alice) is not None
    finally:
        db.close()


def test_mark_needs_reconnect_without_link_is_a_no_op(client, keycloak, usos):
    login(client, keycloak)
    db = client.session_factory()
    try:
        mark_needs_reconnect(db, _user_id(client, "alice"))
        assert unlink(db, _cipher(), usos.client, _user_id(client, "alice")) is False
    finally:
        db.close()


def test_tokens_never_reach_the_logs(client, keycloak, usos, caplog):
    login(client, keycloak)
    with caplog.at_level(logging.DEBUG):
        token, verifier = usos.authorize(_start(client))
        client.get("/usos/callback", params={"oauth_token": token, "oauth_verifier": verifier}, follow_redirects=False)
        client.get("/usos/status")
        client.delete("/usos/link", headers=ORIGIN)

    request = next(iter(usos.request_tokens.values()))
    secrets_seen = [token, verifier, request.secret, CONSUMER_SECRET, *usos.revoked]
    assert usos.revoked
    for record in caplog.records:
        # httpx2 = TestClient Starlette (strona "przegladarki"), nie backend
        if record.name == "httpx2":
            continue
        assert not record.name.startswith(("httpx", "httpcore", "oauthlib")), record.name
        message = record.getMessage()
        for secret in secrets_seen:
            assert secret not in message, record.name


# --- usuwanie konta -------------------------------------------------------

def test_deleting_account_removes_link(client, keycloak, usos):
    login(client, keycloak)
    _connect(client, usos)
    db = client.session_factory()
    try:
        user = db.get(User, _user_id(client, "alice"))
        db.delete(user)
        db.commit()
    finally:
        db.close()

    assert _links(client) == []


def test_foreign_key_cascades_on_raw_delete(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fk.db'}")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(oidc_sub="carol")
        db.add(user)
        db.flush()
        db.add(UsosLink(user_id=user.id, usos_user_id="1", token_enc="x", scopes="studies"))
        db.commit()
        db.execute(text("DELETE FROM users"))
        db.commit()
        assert db.execute(select(UsosLink)).first() is None
    engine.dispose()
