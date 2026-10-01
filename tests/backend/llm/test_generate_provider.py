"""
Testy wyboru dostawcy LLM (LLM_PROVIDER) w provider.py i generate.py.
"""

import pytest

from src.backend.llm import claude_client, cursor_client, generate, ollama_client, openrouter_client
from src.backend.llm.provider import current_provider, env_setting
from src.backend.rag.context_builder import RagContext


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


SOURCES = [{"kind": "mordor", "title": "plan.png", "url": None}]


def _fake_rag(monkeypatch):
    monkeypatch.setattr(generate, "condense", lambda query, history: query)
    monkeypatch.setattr(
        generate,
        "retrieve_context",
        lambda query, k_mordor, k_other: RagContext("kontekst", ["a/b/plan.png"], list(SOURCES)),
    )


def test_answer_returns_answer_files_and_sources(monkeypatch):
    _fake_rag(monkeypatch)
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return "odpowiedz"

    monkeypatch.setattr(generate, "_resolve_chat_fn", lambda: fake_chat)

    result = generate.answer("gdzie jest sala 0004?")

    assert result == {"answer": "odpowiedz", "files": ["a/b/plan.png"], "sources": SOURCES}
    assert "KONTEKST TEKSTOWY:\nkontekst" in seen["user"]
    assert "- plan.png (folder: b)" in seen["user"]
    assert seen["user"].endswith("Odpowiedz po polsku.")
    assert "po polsku" in seen["system"]


def test_answer_uses_chosen_language_in_prompts(monkeypatch):
    _fake_rag(monkeypatch)
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return "answer"

    monkeypatch.setattr(generate, "_resolve_chat_fn", lambda: fake_chat)

    generate.answer("gdzie jest sala 0004?", language="en")

    assert seen["user"].endswith("Answer in English.")
    assert "po angielsku" in seen["system"]
    assert "po polsku" not in seen["system"]
    assert "chinskiego" in seen["system"]


def test_stream_answer_streams_chunks_with_same_prompt(monkeypatch):
    _fake_rag(monkeypatch)
    seen = {}

    def fake_stream(**kwargs):
        seen.update(kwargs)
        yield "Sala "
        yield "0004."

    monkeypatch.setattr(generate, "_resolve_stream_fn", lambda: fake_stream)
    history = [{"role": "user", "content": "hej"}, {"role": "assistant", "content": "czesc"}]

    stream = generate.stream_answer("gdzie jest sala 0004?", history=history, language="fr")

    assert stream.sources == SOURCES
    assert stream.files == ["a/b/plan.png"]
    assert list(stream.chunks) == ["Sala ", "0004."]
    assert seen["user"].endswith("Réponds en français.")
    assert "po francusku" in seen["system"]
    assert seen["history"] == history


@pytest.mark.parametrize(
    ("provider", "stream_fn"),
    [
        ("ollama", ollama_client.stream_chat),
        ("claude", claude_client.stream_chat),
        ("cursor", cursor_client.stream_chat),
        ("openrouter", openrouter_client.stream_chat),
    ],
)
def test_stream_fn_follows_provider(monkeypatch, provider, stream_fn):
    monkeypatch.setenv("LLM_PROVIDER", provider)

    assert generate._resolve_stream_fn() is stream_fn


@pytest.mark.parametrize("language", ["pl", "en", "fr"])
def test_system_prompt_rules_are_separate_lines(language):
    lines = generate.system_prompt(language).splitlines()

    for number in range(1, 8):
        assert sum(line.startswith(f"{number}. ") for line in lines) == 1
