"""
Testy rewrite.py - kondensacja zapytania przed retrievalem. Bez wywolan
modelu: chat() jest podmieniany na atrape.
"""

import os
import sys

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "backend")
)
sys.path.insert(0, BACKEND_DIR)

from llm import rewrite


def test_returns_query_unchanged_without_history():
    assert rewrite.condense("kim jest Jan Kowalski", None) == "kim jest Jan Kowalski"
    assert rewrite.condense("kim jest Jan Kowalski", []) == "kim jest Jan Kowalski"


def test_uses_model_output_when_valid(monkeypatch):
    monkeypatch.setattr(rewrite, "chat", lambda **kwargs: "jakie dyzury ma Jan Kowalski")
    history = [{"role": "user", "content": "kim jest Jan Kowalski"}]

    assert rewrite.condense("a jakie ma dyzury?", history) == "jakie dyzury ma Jan Kowalski"


def test_falls_back_to_query_when_model_fails(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("ollama padlo")

    monkeypatch.setattr(rewrite, "chat", boom)
    history = [{"role": "user", "content": "kim jest Jan Kowalski"}]

    assert rewrite.condense("a jakie ma dyzury?", history) == "a jakie ma dyzury?"


def test_rejects_empty_and_overlong_output(monkeypatch):
    history = [{"role": "user", "content": "kim jest Jan Kowalski"}]

    monkeypatch.setattr(rewrite, "chat", lambda **kwargs: "   ")
    assert rewrite.condense("a jakie ma dyzury?", history) == "a jakie ma dyzury?"

    monkeypatch.setattr(rewrite, "chat", lambda **kwargs: "x" * (rewrite.MAX_LENGTH + 1))
    assert rewrite.condense("a jakie ma dyzury?", history) == "a jakie ma dyzury?"


def test_strips_quotes_and_extra_lines(monkeypatch):
    monkeypatch.setattr(
        rewrite, "chat", lambda **kwargs: '"jakie dyzury ma Jan Kowalski"\nDodatkowy komentarz.'
    )
    history = [{"role": "user", "content": "kim jest Jan Kowalski"}]

    assert rewrite.condense("a jakie ma dyzury?", history) == "jakie dyzury ma Jan Kowalski"


def test_ignores_assistant_messages_in_history(monkeypatch):
    seen = {}

    def fake_chat(**kwargs):
        seen["user"] = kwargs["user"]
        return "przepisane zapytanie"

    monkeypatch.setattr(rewrite, "chat", fake_chat)
    history = [
        {"role": "user", "content": "kim jest Jan Kowalski"},
        {"role": "assistant", "content": "ZMYSLONA ODPOWIEDZ MODELU"},
    ]
    rewrite.condense("a jakie ma dyzury?", history)

    assert "kim jest Jan Kowalski" in seen["user"]
    assert "ZMYSLONA" not in seen["user"]


def test_switch_off_skips_model(monkeypatch):
    monkeypatch.setenv("CHAT_CONDENSE", "off")
    monkeypatch.setattr(rewrite, "chat", lambda **kwargs: "NIE POWINNO ZOSTAC UZYTE")
    history = [{"role": "user", "content": "kim jest Jan Kowalski"}]

    assert rewrite.condense("a jakie ma dyzury?", history) == "a jakie ma dyzury?"
