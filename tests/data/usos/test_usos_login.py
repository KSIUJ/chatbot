import pytest
from requests_oauthlib import OAuth1

import usos_api
import usos_login


def test_parse_oauth_response_parses_form_encoded_string():
    result = usos_login.parse_oauth_response(
        "oauth_token=abc123&oauth_token_secret=xyz789&oauth_callback_confirmed=true"
    )

    assert result == {
        "oauth_token": "abc123",
        "oauth_token_secret": "xyz789",
        "oauth_callback_confirmed": "true",
    }


def test_build_authorize_url():
    url = usos_login.build_authorize_url("abc123")

    assert url == "https://apps.usos.uj.edu.pl/services/oauth/authorize?oauth_token=abc123"


def test_update_env_file_replaces_existing_lines(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "USOS_CONSUMER_KEY=abc\nUSOS_CONSUMER_SECRET=def\n", encoding="utf-8"
    )

    usos_login.update_env_file(
        str(env_path),
        {"USOS_CONSUMER_KEY": "new_key", "USOS_ACCESS_TOKEN": "tok123"},
    )

    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert "USOS_CONSUMER_KEY=new_key" in lines
    assert "USOS_CONSUMER_SECRET=def" in lines
    assert "USOS_ACCESS_TOKEN=tok123" in lines


def test_update_env_file_creates_file_if_missing(tmp_path):
    env_path = tmp_path / ".env"

    usos_login.update_env_file(str(env_path), {"USOS_ACCESS_TOKEN": "tok123"})

    assert env_path.read_text(encoding="utf-8") == "USOS_ACCESS_TOKEN=tok123\n"


def test_get_request_token_signs_with_oob_callback_and_scopes(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_login, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 200
        text = "oauth_token=req_tok&oauth_token_secret=req_sec&oauth_callback_confirmed=true"

    captured = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["auth"] = auth
        return FakeResponse()

    monkeypatch.setattr(usos_login.requests, "get", fake_get)

    oauth_token, oauth_token_secret = usos_login.get_request_token()

    assert oauth_token == "req_tok"
    assert oauth_token_secret == "req_sec"
    assert captured["url"] == "https://apps.usos.uj.edu.pl/services/oauth/request_token"
    assert captured["params"] == {"oauth_callback": "oob", "scopes": "other_emails|offline_access"}
    assert isinstance(captured["auth"], OAuth1)
    assert captured["auth"].client.callback_uri == "oob"


def test_get_request_token_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_login, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 401
        text = "invalid consumer"

    monkeypatch.setattr(usos_login.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(usos_api.UsosApiError) as exc_info:
        usos_login.get_request_token()

    assert exc_info.value.status_code == 401


def test_exchange_for_access_token_signs_with_verifier_and_returns_tokens(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_login, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 200
        text = "oauth_token=acc_tok&oauth_token_secret=acc_sec"

    captured = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["auth"] = auth
        return FakeResponse()

    monkeypatch.setattr(usos_login.requests, "get", fake_get)

    access_token, access_token_secret = usos_login.exchange_for_access_token(
        "req_tok", "req_sec", "1234"
    )

    assert access_token == "acc_tok"
    assert access_token_secret == "acc_sec"
    assert captured["url"] == "https://apps.usos.uj.edu.pl/services/oauth/access_token"
    assert captured["auth"].client.resource_owner_key == "req_tok"
    assert captured["auth"].client.resource_owner_secret == "req_sec"
    assert captured["auth"].client.verifier == "1234"


def test_exchange_for_access_token_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_login, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 401
        text = "invalid verifier"

    monkeypatch.setattr(usos_login.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(usos_api.UsosApiError) as exc_info:
        usos_login.exchange_for_access_token("req_tok", "req_sec", "0000")

    assert exc_info.value.status_code == 401
