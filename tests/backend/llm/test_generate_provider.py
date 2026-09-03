"""
Testy przelacznika dostawcy LLM w generate.py - wyboru miedzy lokalnym Ollama
(domyslnie) a API zdalnymi (Claude, OpenRouter) na podstawie zmiennej
srodowiskowej LLM_PROVIDER. Reszta generate.py (budowanie promptu z RAG,
main()) nie ma dotad testow i pozostaje poza zakresem tej zmiany.
"""

from backend.llm import claude_client, generate, openrouter_client
from backend.llm import client as ollama_client


def test_defaults_to_ollama_when_env_var_missing(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    assert generate._resolve_chat_fn() is ollama_client.chat


def test_selects_ollama_explicitly(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    assert generate._resolve_chat_fn() is ollama_client.chat


def test_selects_claude_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude")

    assert generate._resolve_chat_fn() is claude_client.chat


def test_selects_openrouter_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")

    assert generate._resolve_chat_fn() is openrouter_client.chat


def test_falls_back_to_ollama_on_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouterr")

    assert generate._resolve_chat_fn() is ollama_client.chat


def test_provider_env_var_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "CLAUDE")

    assert generate._resolve_chat_fn() is claude_client.chat


def test_openrouter_provider_env_var_tolerates_whitespace_and_case(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "  OpenRouter  ")

    assert generate._resolve_chat_fn() is openrouter_client.chat
