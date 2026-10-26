"""
Czesci polaczenia z USOS bez API: konfiguracja z env, szyfrogram tokenu
zwiazany z kontem, ciasteczko laczenia i podpisy OAuth 1.0a klienta
(sprawdzane niezalezna implementacja z fake_usos.py).
"""

from __future__ import annotations

import httpx
import pytest

from src.backend.auth.crypto import DecryptionError, TokenCipher
from src.backend.auth.settings import load_auth_settings
from src.backend.usos.client import UsosApiError, UsosClient, UsosUnauthorizedError, UsosUnavailableError
from src.backend.usos.crypto import ConnectState, UserToken, UsosTokenCipher
from src.backend.usos.settings import UsosConfigError, load_usos_settings

from fake_usos import CONSUMER_KEY, CONSUMER_SECRET, signature_valid

SECRET_KEY = "test-secret-key-that-is-long-enough-1234567890"


def _auth(redirect_uri: str = "https://chat.ksi.sh/api/auth/callback"):
    return load_auth_settings({
        "OIDC_ISSUER": "https://auth.test/realms/ksi",
        "OIDC_CLIENT_ID": "chatbot",
        "OIDC_CLIENT_SECRET": "x",
        "OIDC_REDIRECT_URI": redirect_uri,
        "AUTH_SECRET_KEY": SECRET_KEY,
    })


def _settings(**env: str):
    base = {"USOS_CONNECT": "on", "USOS_CONSUMER_KEY": CONSUMER_KEY, "USOS_CONSUMER_SECRET": CONSUMER_SECRET}
    return load_usos_settings({**base, **env}, _auth())


# --- konfiguracja --------------------------------------------------------

def test_defaults():
    settings = _settings()

    assert settings.available is True
    assert settings.scopes == "studies|grades|crstests|student_exams|offline_access"
    assert settings.callback_url == "https://chat.ksi.sh/api/usos/callback"
    assert settings.http_timeout_seconds == 10.0
    assert CONSUMER_SECRET not in repr(settings) and CONSUMER_KEY not in repr(settings)


def test_unavailable_without_switch_or_key():
    assert load_usos_settings({}, _auth()).available is False
    assert load_usos_settings({"USOS_CONSUMER_KEY": CONSUMER_KEY, "USOS_CONSUMER_SECRET": "s"}, _auth()).available is False
    assert load_usos_settings({"USOS_CONNECT": "on"}, _auth()).available is False
    # zly klucz scrapera nie zatrzymuje startu, dopoki funkcja jest wylaczona
    assert load_usos_settings({"USOS_CONSUMER_KEY": "zly klucz!"}, _auth()).available is False


def test_callback_follows_login_redirect_uri():
    local = load_usos_settings({}, _auth("http://localhost:5173/api/auth/callback"))
    assert local.callback_url == "http://localhost:5173/api/usos/callback"
    other = load_usos_settings({}, _auth("https://chat.ksi.sh/oidc"))
    assert other.callback_url == "https://chat.ksi.sh/api/usos/callback"
    explicit = _settings(USOS_CALLBACK_URL="https://chat.ksi.sh/x/usos/callback")
    assert explicit.callback_url == "https://chat.ksi.sh/x/usos/callback"


def test_scopes_are_normalized():
    assert _settings(USOS_SCOPES=" studies | grades |studies").scopes == "studies|grades"


@pytest.mark.parametrize("env, message", [
    ({"USOS_CONSUMER_SECRET": ""}, "USOS_CONSUMER_SECRET"),
    ({"USOS_CONSUMER_KEY": "klucz ze spacja"}, "USOS_CONSUMER_KEY"),
    ({"USOS_CONNECT": "moze"}, "USOS_CONNECT"),
    ({"USOS_SCOPES": "studies|Grades"}, "USOS_SCOPES"),
    ({"USOS_CALLBACK_URL": "http://chat.ksi.sh/api/usos/callback"}, "USOS_CALLBACK_URL"),
    ({"USOS_CALLBACK_URL": "https://chat.ksi.sh/api/usos/callback?x=1"}, "USOS_CALLBACK_URL"),
    ({"USOS_HTTP_TIMEOUT": "nan"}, "USOS_HTTP_TIMEOUT"),
    ({"USOS_HTTP_TIMEOUT": "-1"}, "USOS_HTTP_TIMEOUT"),
])
def test_invalid_configuration(env, message):
    with pytest.raises(UsosConfigError, match=message):
        _settings(**env)


# --- szyfrogram tokenu ----------------------------------------------------

def test_token_ciphertext_is_bound_to_account():
    cipher = UsosTokenCipher(SECRET_KEY)
    sealed = cipher.seal("alice", "tokenAAAA1234", "secretBBBB5678")

    token = cipher.unseal("alice", sealed)
    assert (token.token, token.secret) == ("tokenAAAA1234", "secretBBBB5678")
    assert "tokenAAAA1234" not in sealed
    with pytest.raises(DecryptionError):
        cipher.unseal("bob", sealed)


def test_token_key_is_separate_from_login_key():
    login_cipher = TokenCipher(SECRET_KEY)
    sealed = UsosTokenCipher(SECRET_KEY).seal("alice", "tokenAAAA1234", "secretBBBB5678")

    with pytest.raises(DecryptionError):
        login_cipher.decrypt(sealed)
    # szyfrogram kluczem logowania (np. z sesji) nie przejdzie jako token USOS
    with pytest.raises(DecryptionError):
        UsosTokenCipher(SECRET_KEY).unseal("alice", login_cipher.encrypt('{"uid":"alice","t":"a","s":"b","v":1}'))


def test_token_rejects_unknown_format():
    cipher = UsosTokenCipher(SECRET_KEY)
    raw = cipher._cipher
    for payload in ('{"uid":"alice","t":"a","s":"b","v":2}', '{"uid":"alice","t":1,"s":"b","v":1}', "[]", "x"):
        with pytest.raises(DecryptionError):
            cipher.unseal("alice", raw.encrypt(payload))


def test_secrets_are_not_in_repr():
    token = UserToken(user_id="alice", token="tokenAAAA1234", secret="secretBBBB5678")
    state = ConnectState.new("reqtoken1234", "reqsecret5678", "alice", "studies")

    assert "tokenAAAA1234" not in repr(token) and "secretBBBB5678" not in repr(token)
    assert "reqsecret5678" not in repr(state)


def test_connect_state_round_trip():
    cipher = TokenCipher(SECRET_KEY)
    state = ConnectState.new("reqtoken1234", "reqsecret5678", "alice", "studies|grades")

    assert ConnectState.unseal(state.seal(cipher), cipher, 600) == state
    with pytest.raises(DecryptionError):
        ConnectState.unseal(state.seal(TokenCipher("y" * 40)), cipher, 600)


# --- podpisy i bledy klienta -----------------------------------------------

class _Recorder:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        return self.response


def _client(response: httpx.Response) -> tuple[UsosClient, _Recorder]:
    recorder = _Recorder(response)
    return UsosClient(_settings(), httpx.Client(transport=httpx.MockTransport(recorder))), recorder


def test_request_token_is_signed_with_callback_and_scopes():
    client, recorder = _client(httpx.Response(200, text="oauth_token=abcdefgh12&oauth_token_secret=ijklmnop34&x=1"))

    assert client.request_token() == ("abcdefgh12", "ijklmnop34")

    [request] = recorder.requests
    assert request.method == "POST"
    assert str(request.url) == "https://apps.usos.uj.edu.pl/services/oauth/request_token"
    assert request.content == b"scopes=studies%7Cgrades%7Ccrstests%7Cstudent_exams%7Coffline_access"
    header = request.headers["authorization"]
    assert 'oauth_callback="https%3A%2F%2Fchat.ksi.sh%2Fapi%2Fusos%2Fcallback"' in header
    assert 'oauth_signature_method="HMAC-SHA1"' in header
    assert signature_valid(request, CONSUMER_SECRET, "")
    assert not signature_valid(request, "zly-sekret", "")


def test_user_call_is_signed_with_token_and_params_in_body():
    client, recorder = _client(httpx.Response(200, json={"ok": True}))
    token = UserToken(user_id="alice", token="tokenAAAA1234", secret="secretBBBB5678")

    assert client.call(token, "services/tt/user", start="2026-10-26", days=7, fields=["a", "b"], skip=None, flag=True) == {"ok": True}

    [request] = recorder.requests
    assert request.url.query == b""
    assert request.content == b"start=2026-10-26&days=7&fields=a%7Cb&flag=true"
    assert 'oauth_token="tokenAAAA1234"' in request.headers["authorization"]
    assert "secretBBBB5678" not in request.headers["authorization"]
    assert signature_valid(request, CONSUMER_SECRET, "secretBBBB5678")
    assert not signature_valid(request, CONSUMER_SECRET, "innySekret")


def test_access_token_carries_verifier():
    client, recorder = _client(httpx.Response(200, text="oauth_token=abcdefgh12&oauth_token_secret=ijklmnop34"))

    client.access_token("reqtoken1234", "reqsecret5678", "12345678")

    [request] = recorder.requests
    assert 'oauth_verifier="12345678"' in request.headers["authorization"]
    assert signature_valid(request, CONSUMER_SECRET, "reqsecret5678")


@pytest.mark.parametrize("response, error", [
    (httpx.Response(401, text="Invalid token"), UsosUnauthorizedError),
    (httpx.Response(503), UsosUnavailableError),
    (httpx.Response(429), UsosUnavailableError),
    (httpx.Response(302, headers={"location": "https://evil.example/"}), UsosApiError),
    (httpx.Response(403, json={"message": "no", "error": "method_forbidden", "reason": "scope_missing"}), UsosApiError),
    (httpx.Response(200, text="not json"), UsosApiError),
])
def test_errors_are_mapped(response, error):
    client, _ = _client(response)
    token = UserToken(user_id="alice", token="tokenAAAA1234", secret="secretBBBB5678")

    with pytest.raises(error) as caught:
        client.call(token, "services/grades/terms2")
    assert "secretBBBB5678" not in str(caught.value) and "tokenAAAA1234" not in str(caught.value)
    if isinstance(caught.value, UsosApiError) and response.status_code == 403:
        assert caught.value.code == "method_forbidden" and caught.value.reason == "scope_missing"


def test_network_errors_are_unavailable():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = UsosClient(_settings(), httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(UsosUnavailableError):
        client.request_token()


def test_bad_token_response_is_rejected():
    client, _ = _client(httpx.Response(200, text="oauth_token=a b&oauth_token_secret=\n"))

    with pytest.raises(UsosApiError):
        client.request_token()


def test_method_names_are_validated():
    client, recorder = _client(httpx.Response(200, json={}))
    token = UserToken(user_id="alice", token="tokenAAAA1234", secret="secretBBBB5678")

    for method in ("../services/x", "https://evil.example/services/a/b", "services/a/b?x=1"):
        with pytest.raises(ValueError):
            client.call(token, method)
    assert recorder.requests == []
