"""Wspolne fixtury testow API: konfiguracja OIDC w env, atrapa Keycloaka
(z fake_keycloak.py), atrapa LLM i klient z baza w tmp."""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.backend import main as main_module
from src.backend.auth import dependencies as auth_dependencies
from src.backend.auth.oidc import OIDCClient
from src.backend.auth.settings import get_auth_settings
from src.backend.database import get_db, get_session_factory
from src.backend.history import get_history_settings
from src.backend.llm.generate import AnswerStream
from src.backend.models import Base, User

from fake_keycloak import (
    CLIENT_ID,
    CLIENT_SECRET,
    ISSUER,
    MEMBER_GROUP,
    REDIRECT_URI,
    FakeKeycloak,
)

# zrodla, ktore atrapa LLM dolacza do kazdej odpowiedzi
FAKE_SOURCES = [
    {"kind": "strony", "title": "matinf.uj.edu.pl/dziekanat", "url": "https://matinf.uj.edu.pl/dziekanat"},
    {"kind": "mordor", "title": "regulamin.pdf", "url": None},
]

TEST_ENV = {
    "OIDC_ISSUER": ISSUER,
    "OIDC_CLIENT_ID": CLIENT_ID,
    "OIDC_CLIENT_SECRET": CLIENT_SECRET,
    "OIDC_REDIRECT_URI": REDIRECT_URI,
    "AUTH_SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
    "OIDC_REQUIRED_GROUP": MEMBER_GROUP,
    "FRONTEND_ORIGINS": "http://localhost:5173",
}


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch):
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)
    for name in ("AUTH_COOKIE_SECURE", "AUTH_FRONTEND_URL", "OIDC_POST_LOGOUT_REDIRECT_URI", "OIDC_SCOPES",
                 "OIDC_ADMIN_GROUP"):
        monkeypatch.delenv(name, raising=False)
    for name in ("CHAT_HISTORY_MAX_PER_USER", "CHAT_HISTORY_RETENTION_DAYS", "CHAT_HISTORY_PURGE_INTERVAL_HOURS"):
        monkeypatch.delenv(name, raising=False)
    get_auth_settings.cache_clear()
    get_history_settings.cache_clear()
    auth_dependencies._cipher_for.cache_clear()
    auth_dependencies._oidc_client_for.cache_clear()
    yield
    get_auth_settings.cache_clear()
    get_history_settings.cache_clear()
    auth_dependencies._cipher_for.cache_clear()
    auth_dependencies._oidc_client_for.cache_clear()


@pytest.fixture
def fake_sources() -> list[dict[str, str | None]]:
    return FAKE_SOURCES


@pytest.fixture
def keycloak() -> FakeKeycloak:
    return FakeKeycloak()


@pytest.fixture
def session_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def client(auth_env, keycloak: FakeKeycloak, session_factory, monkeypatch: pytest.MonkeyPatch):
    """Klient z pelnym przeplywem OIDC przeciw atrapie Keycloaka."""

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def override_oidc_client() -> OIDCClient:
        return oidc

    oidc = OIDCClient(get_auth_settings(), httpx.Client(transport=httpx.MockTransport(keycloak.handler)))

    calls: list[dict[str, object]] = []

    def fake_answer(message, history=None, language="pl", **kwargs):
        calls.append({"message": message, "history": list(history or []), "language": language})
        return {"answer": f"odpowiedz na: {message}", "files": [], "sources": list(FAKE_SOURCES)}

    def fake_stream(message, history=None, language="pl", **kwargs):
        calls.append({"message": message, "history": list(history or []), "language": language})
        return AnswerStream(
            chunks=iter(["odpowiedz ", "na: ", message]), files=[], sources=list(FAKE_SOURCES)
        )

    monkeypatch.setattr(main_module, "rag_answer", fake_answer)
    monkeypatch.setattr(main_module, "rag_stream", fake_stream)
    # petla kasujaca stare rozmowy dzialalaby na prawdziwej bazie (DATABASE_URL)
    monkeypatch.setattr(main_module, "start_retention_task", lambda: None)
    app = main_module.app
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[auth_dependencies.get_oidc_client] = override_oidc_client

    with TestClient(app, base_url="https://chat.test") as test_client:
        test_client.calls = calls
        test_client.session_factory = session_factory
        test_client.keycloak = keycloak
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def member_override(session_factory):
    """Podmienia require_member na stalego czlonka - do testow, ktore nie
    dotycza samego logowania (np. /chat)."""
    db = session_factory()
    user = User(oidc_sub="test-member", email="member@student.uj.edu.pl", name="Test Member")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()

    def fake_member(db: Session = Depends(get_db)) -> User:
        member = db.get(User, user_id)
        assert member is not None
        return member

    main_module.app.dependency_overrides[auth_dependencies.require_member] = fake_member
    return user_id
