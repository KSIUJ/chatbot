"""
Testy jednostkowe konfiguracji logowania (env), kryptografii i dopasowania grup.
"""

import time
import unicodedata
from types import SimpleNamespace

import pytest
from cryptography import fernet

from src.backend.auth.crypto import DecryptionError, LoginState, TokenCipher, pkce_challenge
from src.backend.auth.service import is_member
from src.backend.auth.settings import LOGIN_STATE_MAX_AGE_SECONDS, AuthConfigError, load_auth_settings
from src.backend.config import parse_origins

BASE_ENV = {
    "OIDC_ISSUER": "https://auth.ksi.sh/realms/ksi",
    "OIDC_CLIENT_ID": "chatbot",
    "OIDC_CLIENT_SECRET": "secret",
    "OIDC_REDIRECT_URI": "https://chat.ksi.sh/api/auth/callback",
    "AUTH_SECRET_KEY": "x" * 40,
}


def test_defaults_for_production():
    s = load_auth_settings(BASE_ENV)

    assert s.required_group == "/Członek"
    assert s.groups_claim == "groups"
    assert s.scopes == "openid profile email"
    assert s.cookie_secure is True
    assert s.session_cookie_name == "__Host-chatbot_session"
    assert s.post_logout_redirect_uri == "https://chat.ksi.sh/"
    assert s.frontend_url == "/"
    assert "https://chat.ksi.sh" in s.allowed_origins
    assert "HS256" not in s.id_token_algorithms and "ES256" in s.id_token_algorithms


def test_local_http_redirect_disables_secure_cookie():
    s = load_auth_settings({**BASE_ENV, "OIDC_REDIRECT_URI": "http://localhost:8080/api/auth/callback"})

    assert s.cookie_secure is False
    assert s.session_cookie_name == "chatbot_session"
    assert s.post_logout_redirect_uri == "http://localhost:8080/"


def test_all_missing_variables_reported_at_once():
    with pytest.raises(AuthConfigError) as exc:
        load_auth_settings({})

    message = str(exc.value)
    for name in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI", "AUTH_SECRET_KEY"):
        assert name in message


@pytest.mark.parametrize(
    "override, fragment",
    [
        ({"AUTH_SECRET_KEY": "short"}, "AUTH_SECRET_KEY"),
        ({"OIDC_ISSUER": "http://auth.ksi.sh/realms/ksi"}, "OIDC_ISSUER"),
        ({"OIDC_REDIRECT_URI": "/api/auth/callback"}, "OIDC_REDIRECT_URI"),
        ({"OIDC_SCOPES": "profile email"}, "openid"),
        ({"OIDC_ID_TOKEN_ALGORITHMS": "RS256,HS256"}, "HS256"),
        ({"OIDC_REQUIRED_GROUP": "   "}, "OIDC_REQUIRED_GROUP"),
        ({"AUTH_FRONTEND_URL": "//evil.example"}, "AUTH_FRONTEND_URL"),
        ({"AUTH_SESSION_MAX_AGE_HOURS": "abc"}, "AUTH_SESSION_MAX_AGE_HOURS"),
        ({"OIDC_HTTP_TIMEOUT": "0"}, "OIDC_HTTP_TIMEOUT"),
        ({"OIDC_HTTP_TIMEOUT": "-5"}, "OIDC_HTTP_TIMEOUT"),
        ({"OIDC_HTTP_TIMEOUT": "abc"}, "OIDC_HTTP_TIMEOUT"),
        ({"OIDC_HTTP_TIMEOUT": "inf"}, "OIDC_HTTP_TIMEOUT"),
    ],
)
def test_invalid_values_are_rejected(override, fragment):
    with pytest.raises(AuthConfigError, match=fragment):
        load_auth_settings({**BASE_ENV, **override})


def test_http_timeout_accepts_positive_fraction():
    s = load_auth_settings({**BASE_ENV, "OIDC_HTTP_TIMEOUT": "2.5"})

    assert s.http_timeout_seconds == 2.5


def test_frontend_origins_are_trimmed_and_deduplicated():
    s = load_auth_settings({**BASE_ENV, "FRONTEND_ORIGINS": " http://localhost:5173/ , ,https://chat.ksi.sh"})

    assert s.allowed_origins == ("https://chat.ksi.sh", "http://localhost:5173")


def test_parse_origins_skips_blanks_and_trailing_slash():
    assert parse_origins("a.example, https://b.example/ ,, /") == ["a.example", "https://b.example"]


def test_is_member_normalizes_unicode_and_matches_exactly():
    group = "/Członkowie Zarządu"  # "ą" ma postac rozlozona (NFD)
    s = load_auth_settings({**BASE_ENV, "OIDC_REQUIRED_GROUP": unicodedata.normalize("NFD", group)})

    assert is_member({"groups": [unicodedata.normalize("NFD", group)]}, s)
    assert is_member({"groups": [group]}, s)
    assert not is_member({"groups": [group + "/Sub"]}, s)
    assert not is_member({"groups": "/Członkowie Zarządu"}, s)  # nie lista
    assert not is_member({}, s)


def test_cipher_roundtrip_and_key_separation():
    a, b = TokenCipher("a" * 40), TokenCipher("b" * 40)

    sealed = a.encrypt("token")

    assert a.decrypt(sealed) == "token"
    with pytest.raises(DecryptionError):
        b.decrypt(sealed)
    with pytest.raises(DecryptionError):
        a.decrypt("garbage")


def test_login_state_seal_roundtrip_and_expiry(monkeypatch):
    cipher = TokenCipher("k" * 40)
    state = LoginState.generate()
    sealed = state.seal(cipher)

    assert LoginState.unseal(sealed, cipher, max_age_seconds=LOGIN_STATE_MAX_AGE_SECONDS) == state
    assert state.code_challenge == pkce_challenge(state.code_verifier)
    assert 43 <= len(state.code_verifier) <= 128  # RFC 7636

    later = time.time() + LOGIN_STATE_MAX_AGE_SECONDS + 5
    monkeypatch.setattr(fernet, "time", SimpleNamespace(time=lambda: later))
    with pytest.raises(DecryptionError):
        LoginState.unseal(sealed, cipher, max_age_seconds=LOGIN_STATE_MAX_AGE_SECONDS)


def test_pkce_challenge_matches_rfc7636_example():
    # RFC 7636, Appendix B
    assert pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
