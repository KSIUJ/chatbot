"""Logowanie operatora (pipeline/scrapers/usos/login.py): zapis tokenu do .env
bez psucia reszty pliku i bez wstrzykniecia innych zmiennych."""

from __future__ import annotations

import stat

import pytest

from pipeline.scrapers.usos import login as login_module


def test_update_env_file_replaces_and_appends(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nexport USOS_ACCESS_TOKEN=old\nB=2", encoding="utf-8")

    login_module.update_env_file(env, {"USOS_ACCESS_TOKEN": "new", "USOS_ACCESS_TOKEN_SECRET": "s"})

    assert env.read_text(encoding="utf-8") == "A=1\nUSOS_ACCESS_TOKEN=new\nB=2\nUSOS_ACCESS_TOKEN_SECRET=s\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


class _Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _Session:
    def __init__(self, *texts):
        self.texts = list(texts)
        self.headers = {}

    def post(self, *args, **kwargs):
        return _Response(self.texts.pop(0))


def test_login_rejects_tokens_that_would_inject_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "k")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "s")
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    session = _Session(
        "oauth_token=abcdefgh123&oauth_token_secret=secret123",
        "oauth_token=evil%0AANTHROPIC_BASE_URL%3Dhttps://x&oauth_token_secret=secret123",
    )

    with pytest.raises(SystemExit):
        login_module.login(env, ask=lambda _prompt: "1234", session=session)

    assert env.read_text(encoding="utf-8") == "A=1\n"


def test_login_saves_tokens(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "k")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "s")
    env = tmp_path / ".env"
    session = _Session(
        "oauth_token=abcdefgh123&oauth_token_secret=secret123",
        "oauth_token=TOKEN1234abcd&oauth_token_secret=SECRET5678efgh",
    )

    login_module.login(env, ask=lambda _prompt: "1234", session=session)

    assert env.read_text(encoding="utf-8") == "USOS_ACCESS_TOKEN=TOKEN1234abcd\nUSOS_ACCESS_TOKEN_SECRET=SECRET5678efgh\n"
    assert "SECRET5678efgh" not in capsys.readouterr().out
