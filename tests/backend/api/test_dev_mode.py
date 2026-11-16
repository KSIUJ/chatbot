"""ENV=dev: logowanie zmyslonymi kontami zamiast Keycloaka, tylko z petli zwrotnej."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.backend import main as main_module
from src.backend.auth import dependencies as auth_dependencies
from src.backend.auth.dev import DEV_ACCOUNTS, DevOIDCClient
from src.backend.auth.settings import (
    DEV_SECRET_KEY,
    AuthConfigError,
    get_auth_settings,
    load_auth_settings,
)
from src.backend.database import get_db, get_session_factory

OIDC_VARS = ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI", "AUTH_SECRET_KEY")
LOCAL = ("127.0.0.1", 50000)


@pytest.fixture
def dev_app(auth_env, session_factory, monkeypatch: pytest.MonkeyPatch):
    """Aplikacja w ENV=dev, bez zadnej zmiennej OIDC_* (jak swiezy .env lokalnie)."""
    monkeypatch.setenv("ENV", "dev")
    for name in (*OIDC_VARS, "FRONTEND_ORIGINS", "OIDC_REQUIRED_GROUP"):
        monkeypatch.delenv(name, raising=False)
    get_auth_settings.cache_clear()
    auth_dependencies._oidc_client_for.cache_clear()
    auth_dependencies._cipher_for.cache_clear()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    for task in ("start_retention_task", "start_occasion_task", "start_warmup_task"):
        monkeypatch.setattr(main_module, task, lambda: None)
    app = main_module.app
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    yield app
    app.dependency_overrides.clear()
    get_auth_settings.cache_clear()
    auth_dependencies._oidc_client_for.cache_clear()
    auth_dependencies._cipher_for.cache_clear()


def _login(client: TestClient, account_id: str):
    """Przeplyw jak w przegladarce: /auth/login -> wybor konta -> /auth/callback."""
    to_picker = client.get("/auth/login", follow_redirects=False)
    assert to_picker.status_code == 303
    picker_url = urlsplit(to_picker.headers["location"])
    assert picker_url.path == "/api/auth/dev/login"
    page = client.get("/auth/dev/login", params=parse_qs(picker_url.query))
    assert page.status_code == 200
    links = dict(re.findall(r'href="http://localhost:5173/api(/auth/callback\?[^"]+)"[^>]*><span>([^<]+)<', page.text))
    account = next(a for a in DEV_ACCOUNTS if a.id == account_id)
    callback = next(path for path, name in links.items() if name == account.name).replace("&amp;", "&")
    return client.get(callback, follow_redirects=False)


def test_dev_mode_needs_no_oidc_settings():
    settings = load_auth_settings({"ENV": "dev"})

    assert settings.dev_mode is True
    assert settings.redirect_uri == "http://localhost:5173/api/auth/callback"
    assert settings.secret_key == DEV_SECRET_KEY
    assert settings.cookie_secure is False


def test_production_still_requires_oidc_and_typo_means_prod():
    with pytest.raises(AuthConfigError, match="OIDC_CLIENT_SECRET"):
        load_auth_settings({"ENV": "prod"})
    with pytest.raises(AuthConfigError, match="OIDC_CLIENT_SECRET"):
        load_auth_settings({"ENV": "deev"})


def test_dev_mode_refuses_public_redirect_uri():
    with pytest.raises(AuthConfigError, match="tylko lokalnie"):
        load_auth_settings({"ENV": "dev", "OIDC_REDIRECT_URI": "https://chat.ksi.sh/api/auth/callback"})


def test_dev_oidc_client_is_used(dev_app):
    assert isinstance(auth_dependencies.get_oidc_client(get_auth_settings()), DevOIDCClient)


def test_board_account_logs_in_as_admin(dev_app):
    with TestClient(dev_app, client=LOCAL) as client:
        back = _login(client, "dev-zarzad")
        assert back.status_code == 303
        assert "auth_error" not in back.headers["location"]

        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["name"] == "Zofia Zarządowa"
        assert me.json()["is_admin"] is True


def test_member_is_not_admin_and_accounts_are_separate(dev_app):
    with TestClient(dev_app, client=LOCAL) as client:
        _login(client, "dev-czlonek")
        first = client.get("/auth/me").json()
        assert first["is_admin"] is False

        client.post("/auth/logout")
        _login(client, "dev-czlonkini")
        second = client.get("/auth/me").json()
        assert second["id"] != first["id"]


def test_former_member_is_refused(dev_app):
    with TestClient(dev_app, client=LOCAL) as client:
        back = _login(client, "dev-byly")
        assert "auth_error=not_member" in back.headers["location"]
        assert client.get("/auth/me").status_code == 401


def test_logout_returns_to_home_page(dev_app):
    with TestClient(dev_app, client=LOCAL) as client:
        _login(client, "dev-czlonek")
        assert client.post("/auth/logout").json()["logout_url"] == "http://localhost:5173/"
        assert client.get("/auth/me").status_code == 401


def test_dev_mode_answers_only_loopback(dev_app):
    with TestClient(dev_app, client=("192.168.1.20", 50000)) as client:
        refused = client.get("/auth/login", follow_redirects=False)
        assert refused.status_code == 403
        assert refused.json()["detail"]["code"] == "dev_mode_local_only"
    with TestClient(dev_app, client=LOCAL) as client:
        # vite z --host: przegladarka z sieci przez proxy na 127.0.0.1
        forwarded = client.get("/health", headers={"X-Forwarded-For": "192.168.1.20"})
        assert forwarded.status_code == 403
        assert client.get("/health", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 200


def test_picker_does_not_exist_in_production(client):
    assert client.get("/auth/dev/login").status_code == 404
