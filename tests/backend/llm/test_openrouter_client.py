"""
Testy openrouter_client.py - klienta OpenRouter API, alternatywy dla lokalnej
Ollamy uzywanej gdy LLM_PROVIDER=openrouter. Klient wola requests bezposrednio
(nie ma SDK jak anthropic), wiec zamiast podmieniac caly modul wystarczy
podmienic requests.request - dzieki temu testy nie wykonuja zadnych zapytan
sieciowych ani nie wymagaja klucza API.
"""

import json

import pytest
import requests

from src.backend.llm import openrouter_client


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else _reply("domyslna odpowiedz")
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


def _reply(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class FakeTransport:
    """Podmiana requests.request - zapamietuje ostatnie wywolanie i zwraca
    (albo rzuca) to, co ustawiono z gory."""

    def __init__(self):
        self.last_call = None
        self.response = FakeResponse()
        self.error = None

    def __call__(self, method, url, **kwargs):
        self.last_call = {"method": method, "url": url, **kwargs}
        if self.error is not None:
            raise self.error
        return self.response

    @property
    def payload(self) -> dict:
        return self.last_call["json"]


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    fake = FakeTransport()
    monkeypatch.setattr(requests, "request", fake)
    return fake


def test_chat_posts_system_and_user_message_with_default_model(transport):
    result = openrouter_client.chat(
        system="Jestes asystentem.", user="Jakie sa zasady zaliczenia?"
    )

    assert transport.last_call["method"] == "POST"
    assert transport.last_call["url"].endswith("/chat/completions")
    assert transport.payload["model"] == "google/gemini-2.5-flash"
    assert transport.payload["messages"] == [
        {"role": "system", "content": "Jestes asystentem."},
        {"role": "user", "content": "Jakie sa zasady zaliczenia?"},
    ]
    assert result == "domyslna odpowiedz"


def test_chat_sends_bearer_token_from_env(transport):
    openrouter_client.chat(system="s", user="u")

    assert transport.last_call["headers"]["Authorization"] == "Bearer test-key"


def test_chat_uses_explicit_model_override(transport):
    openrouter_client.chat(system="s", user="u", model="anthropic/claude-sonnet-5")

    assert transport.payload["model"] == "anthropic/claude-sonnet-5"


def test_chat_uses_model_from_env_var_when_not_overridden(transport, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/qwen3.8-max")

    openrouter_client.chat(system="s", user="u")

    assert transport.payload["model"] == "qwen/qwen3.8-max"


def test_chat_falls_back_to_default_model_when_env_var_is_empty(transport, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "   ")

    openrouter_client.chat(system="s", user="u")

    assert transport.payload["model"] == "google/gemini-2.5-flash"


def test_chat_puts_history_between_system_and_current_question(transport):
    history = [
        {"role": "user", "content": "kim jest Jan Kowalski"},
        {"role": "assistant", "content": "To adiunkt."},
    ]

    openrouter_client.chat(system="s", user="a jaki ma pokoj?", history=history)

    assert transport.payload["messages"] == [
        {"role": "system", "content": "s"},
        *history,
        {"role": "user", "content": "a jaki ma pokoj?"},
    ]


def test_chat_strips_whitespace_around_answer(transport):
    transport.response = FakeResponse(payload=_reply("  odpowiedz z marginesami \n"))

    assert openrouter_client.chat(system="s", user="u") == "odpowiedz z marginesami"


def test_chat_raises_runtime_error_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        openrouter_client.chat(system="s", user="u")


def test_chat_raises_runtime_error_on_invalid_key(transport):
    transport.response = FakeResponse(status_code=401, text="unauthorized")

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        openrouter_client.chat(system="s", user="u")


def test_chat_raises_runtime_error_on_insufficient_credits(transport):
    transport.response = FakeResponse(status_code=402, text="payment required")

    with pytest.raises(RuntimeError, match="srodkow"):
        openrouter_client.chat(system="s", user="u")


def test_chat_raises_runtime_error_on_rate_limit(transport):
    transport.response = FakeResponse(status_code=429, text="slow down")

    with pytest.raises(RuntimeError, match="limit"):
        openrouter_client.chat(system="s", user="u")


def test_chat_raises_runtime_error_on_generic_status_error(transport):
    transport.response = FakeResponse(status_code=503, text="upstream exploded")

    with pytest.raises(RuntimeError, match="503"):
        openrouter_client.chat(system="s", user="u")


def test_chat_raises_runtime_error_on_connection_error(transport):
    transport.error = requests.RequestException("network down")

    with pytest.raises(RuntimeError, match="polaczenia"):
        openrouter_client.chat(system="s", user="u")


def test_chat_raises_runtime_error_on_error_inside_successful_response(transport):
    transport.response = FakeResponse(payload={"error": {"message": "provider padl"}})

    with pytest.raises(RuntimeError, match="provider padl"):
        openrouter_client.chat(system="s", user="u")


def test_chat_raises_runtime_error_on_empty_choices(transport):
    transport.response = FakeResponse(payload={"choices": []})

    with pytest.raises(RuntimeError, match="choices"):
        openrouter_client.chat(system="s", user="u")



# --- strumieniowanie (SSE) -----------------------------------------------------


class FakeStreamResponse:
    """Odpowiedz z stream=True: linie SSE, zapamietuje zamkniecie."""

    def __init__(self, lines, status_code=200, text=""):
        self.lines = lines
        self.status_code = status_code
        self.text = text
        self.encoding = None
        self.closed = False

    def iter_lines(self):
        yield from self.lines

    def close(self):
        self.closed = True


def _sse(payload) -> bytes:
    return b"data: " + json.dumps(payload).encode()


def _delta(content: str) -> dict:
    return {"choices": [{"delta": {"role": "assistant", "content": content}}]}


def test_stream_chat_yields_deltas_until_done(transport):
    transport.response = FakeStreamResponse(
        [
            b": OPENROUTER PROCESSING",
            b"",
            _sse(_delta("Dzie")),
            _sse({"choices": [{"delta": {"role": "assistant"}}]}),
            _sse(_delta("kanat ąę")),
            _sse({"choices": []}),
            b"data: [DONE]",
            _sse(_delta("po koncu")),
        ]
    )

    chunks = list(openrouter_client.stream_chat(system="s", user="u"))

    assert chunks == ["Dzie", "kanat ąę"]
    assert transport.payload["stream"] is True
    assert transport.last_call["stream"] is True
    assert transport.last_call["headers"]["Authorization"] == "Bearer test-key"
    assert transport.response.closed


def test_stream_chat_raises_on_error_event(transport):
    transport.response = FakeStreamResponse(
        [_sse(_delta("cz")), _sse({"error": {"message": "provider padl"}, "choices": [{"finish_reason": "error"}]})]
    )

    stream = openrouter_client.stream_chat(system="s", user="u")

    assert next(stream) == "cz"
    with pytest.raises(RuntimeError, match="provider padl"):
        next(stream)
    assert transport.response.closed


def test_stream_chat_maps_http_status_errors(transport):
    transport.response = FakeStreamResponse([], status_code=402, text="payment required")

    with pytest.raises(RuntimeError, match="srodkow"):
        list(openrouter_client.stream_chat(system="s", user="u"))
    assert transport.response.closed


def test_stream_chat_maps_connection_errors(transport):
    transport.error = requests.RequestException("network down")

    with pytest.raises(RuntimeError, match="polaczenia"):
        list(openrouter_client.stream_chat(system="s", user="u"))


def test_closing_stream_early_closes_http_response(transport):
    transport.response = FakeStreamResponse([_sse(_delta("a")), _sse(_delta("b")), b"data: [DONE]"])

    stream = openrouter_client.stream_chat(system="s", user="u")
    assert next(stream) == "a"
    stream.close()

    assert transport.response.closed
