"""
Testy claude_client.py - klienta Claude API (Anthropic), alternatywy dla
lokalnego Ollamy uzywanej gdy LLM_PROVIDER=claude. Podmieniamy modul
"anthropic" na fake'a (ten sam wzorzec co fake_sentence_transformers w
tests/backend/RAG/test_encoder.py), zeby nie wykonywac prawdziwych zapytan
sieciowych ani wymagac klucza API w testach.
"""

import sys
import types

import pytest


class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeMessagesResource:
    def __init__(self, client):
        self._client = client

    def create(self, **kwargs):
        self._client.last_create_kwargs = kwargs
        if self._client.error_to_raise is not None:
            raise self._client.error_to_raise
        return self._client.response_to_return


class FakeAnthropicClient:
    """Podmiana anthropic.Anthropic - zapamietuje kwargs wywolania create() i
    pozwala z gory ustawic (przez atrybuty klasy next_response/next_error),
    co ma zwrocic/rzucic kolejna utworzona instancja."""

    last_instance = None
    next_response = None
    next_error = None

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.response_to_return = FakeAnthropicClient.next_response or FakeResponse(
            [FakeTextBlock("domyslna odpowiedz")]
        )
        self.error_to_raise = FakeAnthropicClient.next_error
        self.last_create_kwargs = None
        self.messages = FakeMessagesResource(self)
        FakeAnthropicClient.last_instance = self


class FakeAuthenticationError(Exception):
    pass


class FakeRateLimitError(Exception):
    pass


class FakeAPIConnectionError(Exception):
    pass


class FakeAPIStatusError(Exception):
    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.status_code = status_code


@pytest.fixture
def fake_anthropic_client(monkeypatch):
    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = FakeAnthropicClient
    fake_module.AuthenticationError = FakeAuthenticationError
    fake_module.RateLimitError = FakeRateLimitError
    fake_module.APIConnectionError = FakeAPIConnectionError
    fake_module.APIStatusError = FakeAPIStatusError
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    monkeypatch.setattr(FakeAnthropicClient, "next_response", None, raising=False)
    monkeypatch.setattr(FakeAnthropicClient, "next_error", None, raising=False)
    return FakeAnthropicClient


def _import_chat():
    from backend.llm.claude_client import chat

    return chat


def test_chat_sends_system_and_user_message_with_default_model(fake_anthropic_client, monkeypatch):
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    chat = _import_chat()

    result = chat(system="Jestes asystentem.", user="Jakie sa zasady zaliczenia?")

    kwargs = fake_anthropic_client.last_instance.last_create_kwargs
    assert kwargs["model"] == "claude-sonnet-5"
    assert kwargs["system"] == "Jestes asystentem."
    assert kwargs["messages"] == [{"role": "user", "content": "Jakie sa zasady zaliczenia?"}]
    assert result == "domyslna odpowiedz"


def test_chat_uses_explicit_model_override(fake_anthropic_client):
    chat = _import_chat()

    chat(system="s", user="u", model="claude-opus-5")

    assert fake_anthropic_client.last_instance.last_create_kwargs["model"] == "claude-opus-5"


def test_chat_uses_model_from_env_var_when_not_overridden(fake_anthropic_client, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-4-5")
    chat = _import_chat()

    chat(system="s", user="u")

    assert fake_anthropic_client.last_instance.last_create_kwargs["model"] == "claude-haiku-4-5"


def test_chat_joins_multiple_text_blocks_from_response(fake_anthropic_client, monkeypatch):
    monkeypatch.setattr(
        fake_anthropic_client,
        "next_response",
        FakeResponse([FakeTextBlock("pierwsza czesc "), FakeTextBlock("druga czesc")]),
    )
    chat = _import_chat()

    result = chat(system="s", user="u")

    assert result == "pierwsza czesc druga czesc"


def test_chat_raises_runtime_error_on_authentication_error(fake_anthropic_client, monkeypatch):
    monkeypatch.setattr(fake_anthropic_client, "next_error", FakeAuthenticationError("invalid key"))
    chat = _import_chat()

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        chat(system="s", user="u")


def test_chat_raises_runtime_error_on_rate_limit_error(fake_anthropic_client, monkeypatch):
    monkeypatch.setattr(fake_anthropic_client, "next_error", FakeRateLimitError("slow down"))
    chat = _import_chat()

    with pytest.raises(RuntimeError, match="limit"):
        chat(system="s", user="u")


def test_chat_raises_runtime_error_on_connection_error(fake_anthropic_client, monkeypatch):
    monkeypatch.setattr(fake_anthropic_client, "next_error", FakeAPIConnectionError("network down"))
    chat = _import_chat()

    with pytest.raises(RuntimeError, match="polaczenia"):
        chat(system="s", user="u")


def test_chat_raises_runtime_error_on_generic_api_status_error(fake_anthropic_client, monkeypatch):
    monkeypatch.setattr(
        fake_anthropic_client, "next_error", FakeAPIStatusError("server exploded", status_code=503)
    )
    chat = _import_chat()

    with pytest.raises(RuntimeError, match="503"):
        chat(system="s", user="u")
