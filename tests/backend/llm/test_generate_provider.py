"""
Testy wyboru dostawcy LLM (LLM_PROVIDER) w provider.py i generate.py.
"""

from src.backend.llm import claude_client, cursor_client, generate, ollama_client, openrouter_client
from src.backend.llm.provider import current_provider, env_setting


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


def test_selects_cursor_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cursor")

    assert generate._resolve_chat_fn() is cursor_client.chat


def test_falls_back_to_ollama_on_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouterr")

    assert current_provider() == "ollama"
    assert generate._resolve_chat_fn() is ollama_client.chat


def test_provider_env_var_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "CLAUDE")

    assert generate._resolve_chat_fn() is claude_client.chat


def test_openrouter_provider_env_var_tolerates_whitespace_and_case(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "  OpenRouter  ")

    assert generate._resolve_chat_fn() is openrouter_client.chat


def test_env_setting_strips_and_falls_back_on_blank(monkeypatch):
    monkeypatch.setenv("SOME_MODEL", "  model-x \n")
    assert env_setting("SOME_MODEL", "domyslny") == "model-x"

    monkeypatch.setenv("SOME_MODEL", "   ")
    assert env_setting("SOME_MODEL", "domyslny") == "domyslny"

    monkeypatch.delenv("SOME_MODEL")
    assert env_setting("SOME_MODEL", "domyslny") == "domyslny"


def test_answer_returns_answer_and_files_only(monkeypatch):
    monkeypatch.setattr(generate, "condense", lambda query, history: query)
    monkeypatch.setattr(
        generate, "build_context", lambda query, k_mordor, k_other: ("kontekst", ["a/b/plan.png"])
    )
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return "odpowiedz"

    monkeypatch.setattr(generate, "_resolve_chat_fn", lambda: fake_chat)

    result = generate.answer("gdzie jest sala 0004?")

    assert result == {"answer": "odpowiedz", "files": ["a/b/plan.png"]}
    assert "KONTEKST TEKSTOWY:\nkontekst" in seen["user"]
    assert "- plan.png (folder: b)" in seen["user"]


def test_system_prompt_rules_are_separate_lines():
    lines = generate.SYSTEM_PROMPT.splitlines()

    for number in range(1, 8):
        assert sum(line.startswith(f"{number}. ") for line in lines) == 1
