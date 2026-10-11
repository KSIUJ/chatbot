"""
Testy rewrite.py - kondensacja zapytania przed retrievalem: model dostawcy
(podmieniany na atrape, bez wywolan API) i regula dla dopytan.
"""

import logging

import pytest

from src.backend.llm import rewrite

HISTORY = [{"role": "user", "content": "kim jest Jan Kowalski"}]


@pytest.fixture(autouse=True)
def ollama_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("CHAT_CONDENSE", raising=False)
    monkeypatch.delenv("CHAT_CONDENSE_TIMEOUT", raising=False)


def _model(monkeypatch, reply=None, error=None, provider="ollama"):
    """Atrapa modelu dostawcy; zwraca slownik z ostatnim wywolaniem."""
    seen = {}

    def fake(system, user):
        seen["system"], seen["user"] = system, user
        if error is not None:
            raise error
        return reply

    monkeypatch.setitem(rewrite._REWRITERS, provider, fake)
    return seen


def test_returns_query_unchanged_without_history():
    assert rewrite.condense("kim jest Jan Kowalski", None) == "kim jest Jan Kowalski"
    assert rewrite.condense("kim jest Jan Kowalski", []) == "kim jest Jan Kowalski"


def test_uses_model_output_when_valid(monkeypatch):
    _model(monkeypatch, "jakie dyzury ma Jan Kowalski")

    assert rewrite.condense("a jakie ma dyzury?", HISTORY) == "jakie dyzury ma Jan Kowalski"


@pytest.mark.parametrize("provider", ["claude", "openrouter"])
def test_api_providers_rewrite_with_their_model(monkeypatch, provider):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    _model(monkeypatch, "jakie dyzury ma Jan Kowalski", provider=provider)

    assert rewrite.condense("a jakie ma dyzury?", HISTORY) == "jakie dyzury ma Jan Kowalski"


def test_model_failure_falls_back_to_the_rule_and_logs(monkeypatch, caplog):
    _model(monkeypatch, error=RuntimeError("ollama padlo"))

    with caplog.at_level(logging.WARNING, logger=rewrite.__name__):
        assert rewrite.condense("a jakie ma dyzury?", HISTORY) == "kim jest Jan Kowalski a jakie ma dyzury?"

    assert "ollama padlo" in caplog.text


def test_empty_and_overlong_output_fall_back_to_the_rule(monkeypatch):
    _model(monkeypatch, "   ")
    assert rewrite.condense("a jakie ma dyzury?", HISTORY) == "kim jest Jan Kowalski a jakie ma dyzury?"

    _model(monkeypatch, "x" * (rewrite.MAX_LENGTH + 1))
    assert rewrite.condense("kiedy jest sesja?", HISTORY) == "kiedy jest sesja?"


def test_strips_quotes_and_extra_lines(monkeypatch):
    _model(monkeypatch, '"jakie dyzury ma Jan Kowalski"\nDodatkowy komentarz.')

    assert rewrite.condense("a jakie ma dyzury?", HISTORY) == "jakie dyzury ma Jan Kowalski"


def test_ignores_assistant_messages_in_history(monkeypatch):
    seen = _model(monkeypatch, "przepisane zapytanie")
    history = [*HISTORY, {"role": "assistant", "content": "ZMYSLONA ODPOWIEDZ MODELU"}]

    rewrite.condense("a jakie ma dyzury?", history)

    assert "kim jest Jan Kowalski" in seen["user"]
    assert "ZMYSLONA" not in seen["user"]


def test_switch_off_skips_model_and_rule(monkeypatch):
    monkeypatch.setenv("CHAT_CONDENSE", "off")
    _model(monkeypatch, "NIE POWINNO ZOSTAC UZYTE")

    assert rewrite.condense("a jakie ma dyzury?", HISTORY) == "a jakie ma dyzury?"


def test_heuristic_mode_skips_model(monkeypatch):
    monkeypatch.setenv("CHAT_CONDENSE", "heuristic")
    _model(monkeypatch, error=AssertionError("model nie powinien byc wolany"))

    assert rewrite.condense("a jakie ma dyzury?", HISTORY) == "kim jest Jan Kowalski a jakie ma dyzury?"


def test_cursor_uses_only_the_rule(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cursor")

    assert "cursor" not in rewrite._REWRITERS
    assert rewrite.condense("a jakie ma dyzury?", HISTORY) == "kim jest Jan Kowalski a jakie ma dyzury?"


def test_rule_takes_the_latest_previous_question(monkeypatch):
    monkeypatch.setenv("CHAT_CONDENSE", "heuristic")
    history = [
        {"role": "user", "content": "kim jest Jan Kowalski"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "Gdzie siedzi Anna Nowak?"},
    ]

    assert rewrite.condense("W którym pokoju go znajdę?", history) == "Gdzie siedzi Anna Nowak? W którym pokoju go znajdę?"


@pytest.mark.parametrize(
    "query",
    ["A kiedy ma dyżury?", "i gdzie ma pokój", "W którym pokoju go znajdę?", "Kto je dostał w tym roku?", "a tam?"],
)
def test_followups_are_recognised(query):
    assert rewrite.looks_like_followup(query)


@pytest.mark.parametrize(
    "query",
    [
        "Kiedy zaczyna się sesja?",
        "A co z dr Anną Nowak?",
        "Co to jest mLegitymacja?",
        "Jakie dokumenty są potrzebne do złożenia wniosku o stypendium rektora dla najlepszych studentów?",
        "",
    ],
)
def test_standalone_questions_are_not_followups(query):
    assert not rewrite.looks_like_followup(query)


def test_claude_request_has_no_temperature_and_a_short_limit(monkeypatch):
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return "przepisane"

    monkeypatch.setattr(rewrite.claude_client, "chat", fake_chat)
    monkeypatch.setenv("CHAT_CONDENSE_TIMEOUT", "5")

    assert rewrite._claude("system", "pytanie") == "przepisane"
    assert "temperature" not in seen
    assert seen["timeout"] == 5
    assert seen["max_tokens"] == rewrite.CLAUDE_MAX_TOKENS


def test_openrouter_request_is_deterministic_and_short(monkeypatch):
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return "przepisane"

    monkeypatch.setattr(rewrite.openrouter_client, "chat", fake_chat)

    assert rewrite._openrouter("system", "pytanie") == "przepisane"
    assert seen["temperature"] == 0.0
    assert seen["timeout"] == rewrite.DEFAULT_TIMEOUT
