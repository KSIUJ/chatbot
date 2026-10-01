"""
Testy logowania OIDC przeciw atrapie Keycloaka (fake_keycloak.FakeKeycloak):
callback, sesje, natychmiastowe odebranie dostepu po usunieciu z grupy,
odswiezanie tokenow, wylogowanie, wlasnosc rozmow i sprawdzanie Origin.
"""

from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from src.backend.auth.crypto import hash_session_token
from src.backend.models import Conversation, User, UserSession

from fake_keycloak import CLIENT_ID, MEMBER_GROUP, login

SESSION_COOKIE = "__Host-chatbot_session"
LOGIN_COOKIE = "__Host-chatbot_login"


def _auth_error(response) -> str | None:
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query.get("auth_error", [None])[0]


def _sessions(client) -> list[UserSession]:
    db = client.session_factory()
    try:
        return list(db.execute(select(UserSession)).scalars())
    finally:
        db.close()


def _users(client) -> list[User]:
    db = client.session_factory()
    try:
        return list(db.execute(select(User)).scalars())
    finally:
        db.close()


# --- /auth/login ---------------------------------------------------------

def test_login_redirects_to_keycloak_with_pkce_and_sets_login_cookie(client):
    r = client.get("/auth/login", follow_redirects=False)

    assert r.status_code == 303
    location = urlsplit(r.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        "https://auth.test/realms/ksi/protocol/openid-connect/auth"
    )
    query = {k: v[0] for k, v in parse_qs(location.query).items()}
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == "https://chat.test/api/auth/callback"
    assert query["code_challenge_method"] == "S256"
    assert query["state"] and query["nonce"] and query["code_challenge"]

    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{LOGIN_COOKIE}=")
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag in cookie


def _login_query(client, url: str) -> dict[str, str]:
    r = client.get(url, follow_redirects=False)
    assert r.status_code == 303
    return {k: v[0] for k, v in parse_qs(urlsplit(r.headers["location"]).query).items()}


def test_login_passes_interface_language_to_keycloak(client):
    query = _login_query(client, "/auth/login?ui_locales=uk")

    assert query["ui_locales"] == "uk"


def test_login_ignores_unsupported_language(client):
    for value in ("xx", "pl en", "", "<script>"):
        query = _login_query(client, f"/auth/login?ui_locales={value}")
        assert "ui_locales" not in query


def test_login_without_prompt_keeps_sso(client):
    query = _login_query(client, "/auth/login")

    assert "prompt" not in query


def test_login_can_force_the_login_form_for_another_account(client):
    query = _login_query(client, "/auth/login?ui_locales=pl&prompt=login")

    assert query["prompt"] == "login"
    assert query["ui_locales"] == "pl"


def test_login_drops_other_prompt_values(client):
    for value in ("none", "consent", "select_account", "login none", "LOGIN", ""):
        query = _login_query(client, f"/auth/login?prompt={value}")
        assert "prompt" not in query


def test_login_when_keycloak_down_returns_to_frontend_with_error(client):
    client.keycloak.down = True

    r = client.get("/auth/login", follow_redirects=False)

    assert r.status_code == 303
    assert _auth_error(r) == "provider_unavailable"


# --- /auth/callback ------------------------------------------------------

def test_member_login_creates_user_and_session(client):
    r = login(client, client.keycloak, "alice")

    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert SESSION_COOKIE in client.cookies

    users = _users(client)
    assert [(u.oidc_sub, u.email, u.name) for u in users] == [
        ("alice", "alice@student.uj.edu.pl", "Alice Testowy")
    ]
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["name"] == "Alice Testowy"


def test_session_cookie_is_hashed_and_tokens_encrypted_in_db(client):
    login(client, client.keycloak, "alice")
    raw = client.cookies[SESSION_COOKIE]

    (session,) = _sessions(client)
    assert session.id == hash_session_token(raw)
    assert raw not in session.id
    # tokeny Keycloaka nie leza w bazie jawnym tekstem
    assert all(t not in session.access_token_enc for t in client.keycloak.access_tokens)
    assert all(t not in (session.refresh_token_enc or "") for t in client.keycloak.refresh_tokens)


def test_non_member_is_refused_and_nothing_is_stored(client):
    r = login(client, client.keycloak, "bob", groups=["/Sympatyk"])

    assert _auth_error(r) == "not_member"
    assert SESSION_COOKIE not in client.cookies
    assert _users(client) == []
    assert _sessions(client) == []


def test_member_group_is_matched_exactly(client):
    # podgrupa albo podobna nazwa to nie to samo co /Członek
    r = login(client, client.keycloak, "carol", groups=["/Członek/Zarząd", "Członek", "/członek"])

    assert _auth_error(r) == "not_member"


def test_missing_groups_claim_is_refused_with_a_hint_in_the_log(client, caplog):
    # klient w Keycloaku bez mappera Group Membership - odmowa ma byc widoczna w logach
    client.keycloak.groups_mapper = False

    with caplog.at_level("INFO", logger="src.backend.auth.router"):
        r = login(client, client.keycloak, "dave")

    assert _auth_error(r) == "not_member"
    assert any(
        rec.levelname == "WARNING" and "'groups' claim" in rec.getMessage() for rec in caplog.records
    )


def test_callback_rejects_state_mismatch(client):
    client.keycloak.add_user("alice")
    start = client.get("/auth/login", follow_redirects=False)
    code, _state = client.keycloak.authorize(start.headers["location"], "alice")

    r = client.get("/auth/callback", params={"code": code, "state": "forged"}, follow_redirects=False)

    assert _auth_error(r) == "invalid_state"
    assert _sessions(client) == []


def test_callback_without_login_cookie_is_rejected(client):
    """Login CSRF: kod+state wygenerowane w innej przegladarce nie dzialaja."""
    client.keycloak.add_user("mallory")
    start = client.get("/auth/login", follow_redirects=False)
    code, state = client.keycloak.authorize(start.headers["location"], "mallory")
    client.cookies.clear()

    r = client.get("/auth/callback", params={"code": code, "state": state}, follow_redirects=False)

    assert _auth_error(r) == "invalid_state"


def test_callback_rejects_wrong_nonce(client):
    client.keycloak.nonce_override = "attacker-nonce"

    r = login(client, client.keycloak, "alice")

    assert _auth_error(r) == "login_failed"
    assert _sessions(client) == []


def test_callback_rejects_token_signed_with_foreign_key(client):
    from joserfc.jwk import ECKey

    # ten sam kid co w JWKS, ale inny klucz - podpis sie nie zgadza
    client.keycloak.signing_key_override = ECKey.generate_key("P-256", parameters={"kid": "k1"})

    r = login(client, client.keycloak, "alice")

    assert _auth_error(r) == "login_failed"
    assert _sessions(client) == []


def test_callback_passes_through_keycloak_error(client):
    r = client.get("/auth/callback", params={"error": "access_denied", "state": "x"}, follow_redirects=False)

    assert _auth_error(r) == "access_denied"


def test_authorization_code_is_single_use(client):
    client.keycloak.add_user("alice")
    start = client.get("/auth/login", follow_redirects=False)
    code, state = client.keycloak.authorize(start.headers["location"], "alice")
    login_cookie = client.cookies[LOGIN_COOKIE]

    first = client.get("/auth/callback", params={"code": code, "state": state}, follow_redirects=False)
    client.cookies.set(LOGIN_COOKIE, login_cookie, domain="chat.test")
    replay = client.get("/auth/callback", params={"code": code, "state": state}, follow_redirects=False)

    assert first.headers["location"] == "/"
    assert _auth_error(replay) == "login_failed"


def test_relogin_reuses_account_and_updates_profile(client):
    login(client, client.keycloak, "alice")
    client.keycloak.users["alice"].name = "Alicja Nowa"

    login(client, client.keycloak, "alice")

    users = _users(client)
    assert len(users) == 1
    assert users[0].name == "Alicja Nowa"


# --- ochrona endpointow i czlonkostwo na biezaco ---------------------------

def test_protected_endpoints_require_login(client):
    assert client.get("/auth/me").json()["detail"]["code"] == "not_authenticated"
    assert client.post("/chat", json={"message": "hej"}).status_code == 401
    assert client.get("/conversations").status_code == 401
    assert client.get("/conversations/abc").status_code == 401


def test_unknown_session_cookie_is_rejected(client):
    client.cookies.set(SESSION_COOKIE, "made-up", domain="chat.test")

    r = client.get("/auth/me")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "session_expired"


def test_removal_from_group_revokes_access_on_next_request(client):
    login(client, client.keycloak, "alice")
    assert client.post("/chat", json={"message": "hej"}).status_code == 200

    client.keycloak.users["alice"].groups = ["/Absolwent"]

    r = client.post("/chat", json={"message": "hej znowu"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_member"
    assert _sessions(client) == []
    # sesja jest skasowana - przywrocenie grupy nie wskrzesza jej
    client.keycloak.users["alice"].groups = [MEMBER_GROUP]
    assert client.get("/auth/me").status_code == 401


def test_membership_is_checked_with_keycloak_on_every_request(client):
    login(client, client.keycloak, "alice")
    before = client.keycloak.calls.count("GET /realms/ksi/protocol/openid-connect/userinfo")

    client.get("/auth/me")
    client.get("/auth/me")

    after = client.keycloak.calls.count("GET /realms/ksi/protocol/openid-connect/userinfo")
    assert after - before == 2


def test_keycloak_logout_ends_app_session(client):
    login(client, client.keycloak, "alice")

    client.keycloak.end_sessions("alice")

    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "session_expired"
    assert _sessions(client) == []


def test_expiring_access_token_is_refreshed_with_rotation(client):
    client.keycloak.access_ttl = 5  # ponizej marginesu 30 s -> odswiezanie przy kazdym zapytaniu
    login(client, client.keycloak, "alice")

    for _ in range(3):
        assert client.get("/auth/me").status_code == 200

    token_calls = client.keycloak.calls.count("POST /realms/ksi/protocol/openid-connect/token")
    assert token_calls == 1 + 3  # wymiana kodu + 3 odswiezenia
    assert len(client.keycloak.refresh_tokens) == 1  # stare refresh tokeny zuzyte


def test_keycloak_outage_fails_closed_but_keeps_session(client):
    login(client, client.keycloak, "alice")

    client.keycloak.down = True
    r = client.post("/chat", json={"message": "hej"})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "provider_unavailable"
    assert len(_sessions(client)) == 1

    client.keycloak.down = False
    assert client.get("/auth/me").status_code == 200


def test_locally_disabled_account_is_logged_out(client):
    login(client, client.keycloak, "alice")
    db = client.session_factory()
    user = db.execute(select(User)).scalar_one()
    user.is_active = False
    db.commit()
    db.close()

    assert client.get("/auth/me").status_code == 401
    # ponowne logowanie tez nie przechodzi
    r = login(client, client.keycloak, "alice")
    assert _auth_error(r) == "login_failed"
    assert _sessions(client) == []


# --- wylogowanie -----------------------------------------------------------

def test_logout_deletes_session_and_returns_keycloak_logout_url(client):
    login(client, client.keycloak, "alice")

    r = client.post("/auth/logout")

    assert r.status_code == 200
    url = urlsplit(r.json()["logout_url"])
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.path == "/realms/ksi/protocol/openid-connect/logout"
    assert query["client_id"] == CLIENT_ID
    assert query["post_logout_redirect_uri"] == "https://chat.test/"
    assert query["id_token_hint"].count(".") == 2
    assert _sessions(client) == []
    assert client.get("/auth/me").status_code == 401


def test_logout_without_session_is_harmless(client):
    r = client.post("/auth/logout")

    assert r.status_code == 200
    assert "id_token_hint" not in r.json()["logout_url"]


# --- rozmowy tylko dla wlasciciela ---------------------------------------

def test_conversations_are_private_to_their_owner(client):
    login(client, client.keycloak, "alice")
    cid = client.post("/chat", json={"message": "pytanie alicji"}).json()["conversation_id"]
    assert client.get(f"/conversations/{cid}").status_code == 200

    client.post("/auth/logout")
    login(client, client.keycloak, "bob")

    assert client.get(f"/conversations/{cid}").status_code == 404
    assert client.post("/chat", json={"message": "hej", "conversation_id": cid}).status_code == 404


def test_new_conversation_belongs_to_user(client):
    login(client, client.keycloak, "alice")

    cid = client.post("/chat", json={"message": "pierwsze pytanie"}).json()["conversation_id"]

    db = client.session_factory()
    conversation = db.get(Conversation, cid)
    owner = db.get(User, conversation.user_id)
    assert owner.oidc_sub == "alice"
    db.close()


# --- Origin ------------------------------------------------------------------

def test_post_from_foreign_origin_is_rejected(client):
    login(client, client.keycloak, "alice")

    r = client.post("/chat", json={"message": "hej"}, headers={"Origin": "https://evil.ksi.sh"})

    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "forbidden_origin"


def test_post_from_own_origin_is_allowed(client):
    login(client, client.keycloak, "alice")

    r = client.post("/chat", json={"message": "hej"}, headers={"Origin": "https://chat.test"})

    assert r.status_code == 200


# --- statystyki -----------------------------------------------------------

def test_stats_count_ksi_accounts(client):
    login(client, client.keycloak, "alice")
    client.post("/auth/logout")
    login(client, client.keycloak, "bob")

    assert client.get("/stats").json()["accounts_created"] == 2
