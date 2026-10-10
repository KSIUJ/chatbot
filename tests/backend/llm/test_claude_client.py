"""
Testy claude_client.py - klienta Claude API (Anthropic), alternatywy dla
lokalnego Ollamy uzywanej gdy LLM_PROVIDER=claude. Podmieniamy modul
"anthropic" na fake'a (ten sam wzorzec co fake_sentence_transformers w
tests/backend/rag/test_encoder.py), zeby nie wykonywac prawdziwych zapytan
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
    def __init__(self, content, stop_reason="end_turn", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class FakeMessagesResource:
    def __init__(self, client):
        self._client = client

    def create(self, **kwargs):
        self._client.last_create_kwargs = kwargs
        if self._client.error_to_raise is not None:
            raise self._client.error_to_raise
        return self._client.response_to_return

    def stream(self, **kwargs):
        self._client.last_stream_kwargs = kwargs
        stream = FakeMessageStream(
            FakeAnthropicClient.next_stream_texts, self._client.error_to_raise, FakeAnthropicClient.next_stream_stop
        )
        self._client.last_stream = stream
        return stream


class FakeMessageStream:
    """Atrapa MessageStream z anthropic: context manager z text_stream."""

    def __init__(self, texts, error, stop_reason="end_turn"):
        self._texts = list(texts)
        self._error = error
        self._stop_reason = stop_reason
        self.closed = False

    def __enter__(self):
        if self._error is not None:
            raise self._error
        return self

    def __exit__(self, *exc_info):
        self.closed = True

    @property
    def text_stream(self):
        yield from self._texts

    def get_final_message(self):
        return FakeResponse([], stop_reason=self._stop_reason, stop_details=types.SimpleNamespace(category="cyber"))


class FakeAnthropicClient:
    """Podmiana anthropic.Anthropic - zapamietuje kwargs wywolania create() i
    pozwala z gory ustawic (przez atrybuty klasy next_response/next_error),
    co ma zwrocic/rzucic kolejna utworzona instancja."""

    last_instance = None
    next_response = None
    next_error = None
    next_stream_texts = ("domyslna ", "odpowiedz")
    next_stream_stop = "end_turn"

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.response_to_return = FakeAnthropicClient.next_response or FakeResponse(
            [FakeTextBlock("domyslna odpowiedz")]
        )
        self.error_to_raise = FakeAnthropicClient.next_error
        self.last_create_kwargs = None
        self.last_stream_kwargs = None
        self.last_stream = None
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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(FakeAnthropicClient, "next_response", None, raising=False)
    monkeypatch.setattr(FakeAnthropicClient, "next_error", None, raising=False)
    monkeypatch.setattr(FakeAnthropicClient, "next_stream_stop", "end_turn", raising=False)
    monkeypatch.delenv("CLAUDE_EFFORT", raising=False)
    return FakeAnthropicClient


def _import_chat():
    from src.backend.llm.claude_client import chat

    return chat


def test_chat_sends_system_and_user_message_with_default_model(fake_anthropic_client, monkeypatch):
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    chat = _import_chat()

    result = chat(system="Jestes asystentem.", user="Jakie sa zasady zaliczenia?")

    kwargs = fake_anthropic_client.last_instance.last_create_kwargs
    assert kwargs["model"] == "claude-haiku-5-5"
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


def test_chat_passes_api_key_from_env_to_client(fake_anthropic_client):
    chat = _import_chat()

    chat(system="s", user="u")

    assert fake_anthropic_client.last_instance.init_kwargs["api_key"] == "test-key"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_chat_raises_runtime_error_when_api_key_missing(fake_anthropic_client, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", value)
    monkeypatch.setattr(fake_anthropic_client, "last_instance", None)
    chat = _import_chat()

    with pytest.raises(RuntimeError, match="Brak klucza Claude API"):
        chat(system="s", user="u")

    assert fake_anthropic_client.last_instance is None


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


def _import_stream_chat():
    from src.backend.llm.claude_client import stream_chat

    return stream_chat


def test_stream_chat_yields_text_pieces(fake_anthropic_client, monkeypatch):
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    monkeypatch.setattr(fake_anthropic_client, "next_stream_texts", ("Dzie", "kanat"))
    stream_chat = _import_stream_chat()
    history = [{"role": "user", "content": "hej"}, {"role": "assistant", "content": "czesc"}]

    chunks = list(stream_chat(system="Jestes asystentem.", user="pytanie", history=history))

    client = fake_anthropic_client.last_instance
    assert chunks == ["Dzie", "kanat"]
    assert client.last_stream_kwargs["model"] == "claude-haiku-5-5"
    assert client.last_stream_kwargs["system"] == "Jestes asystentem."
    assert client.last_stream_kwargs["messages"] == [*history, {"role": "user", "content": "pytanie"}]
    assert client.last_stream.closed


def test_stream_chat_maps_api_errors(fake_anthropic_client, monkeypatch):
    monkeypatch.setattr(fake_anthropic_client, "next_error", FakeRateLimitError("slow down"))
    stream_chat = _import_stream_chat()

    with pytest.raises(RuntimeError, match="limit"):
        list(stream_chat(system="s", user="u"))


def test_stream_chat_requires_api_key(fake_anthropic_client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stream_chat = _import_stream_chat()

    with pytest.raises(RuntimeError, match="Brak klucza Claude API"):
        list(stream_chat(system="s", user="u"))


def test_closing_stream_early_closes_message_stream(fake_anthropic_client, monkeypatch):
    monkeypatch.setattr(fake_anthropic_client, "next_stream_texts", ("a", "b", "c"))
    stream_chat = _import_stream_chat()

    stream = stream_chat(system="s", user="u")
    assert next(stream) == "a"
    stream.close()

    assert fake_anthropic_client.last_instance.last_stream.closed


# --- obrazy (zalaczniki) -----------------------------------------------------------

def test_chat_sends_images_as_base64_blocks_before_text(fake_anthropic_client):
    from src.backend.llm.images import ImageInput

    chat = _import_chat()

    chat(system="s", user="co jest na zdjeciu?", images=[ImageInput("image/png", b"\x89PNG")])

    message = fake_anthropic_client.last_instance.last_create_kwargs["messages"][-1]
    assert message["role"] == "user"
    assert message["content"] == [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw=="}},
        {"type": "text", "text": "co jest na zdjeciu?"},
    ]


def test_stream_chat_sends_images(fake_anthropic_client):
    from src.backend.llm.images import ImageInput

    stream_chat = _import_stream_chat()

    list(stream_chat(system="s", user="u", images=[ImageInput("image/webp", b"RIFF")]))

    content = fake_anthropic_client.last_instance.last_stream_kwargs["messages"][-1]["content"]
    assert content[0]["source"]["media_type"] == "image/webp"
    assert content[-1] == {"type": "text", "text": "u"}


def test_chat_without_images_keeps_plain_text_content(fake_anthropic_client):
    chat = _import_chat()

    chat(system="s", user="u", images=[])

    assert fake_anthropic_client.last_instance.last_create_kwargs["messages"] == [{"role": "user", "content": "u"}]


# --- Claude Haiku 5.5: effort zamiast temperatury, odmowy ---------------------------

def test_request_has_default_effort_and_no_sampling_params(fake_anthropic_client):
    chat = _import_chat()

    chat(system="s", user="u")

    kwargs = fake_anthropic_client.last_instance.last_create_kwargs
    # Haiku 5.5 odrzuca temperature/top_p/top_k inne niz domyslne (400)
    assert not {"temperature", "top_p", "top_k"} & kwargs.keys()
    assert kwargs["output_config"] == {"effort": "medium"}
    assert kwargs["max_tokens"] == 16000


def test_effort_from_env_and_switched_off(fake_anthropic_client, monkeypatch):
    chat = _import_chat()

    monkeypatch.setenv("CLAUDE_EFFORT", " LOW ")
    chat(system="s", user="u")
    assert fake_anthropic_client.last_instance.last_create_kwargs["output_config"] == {"effort": "low"}

    # modele bez effort (np. Haiku 4.5): bez output_config
    monkeypatch.setenv("CLAUDE_EFFORT", "off")
    chat(system="s", user="u")
    assert "output_config" not in fake_anthropic_client.last_instance.last_create_kwargs


def test_invalid_effort_is_a_clear_error(fake_anthropic_client, monkeypatch):
    monkeypatch.setenv("CLAUDE_EFFORT", "turbo")
    chat = _import_chat()

    with pytest.raises(RuntimeError, match="CLAUDE_EFFORT"):
        chat(system="s", user="u")


def test_thinking_blocks_are_left_out_of_the_answer(fake_anthropic_client, monkeypatch):
    thinking = types.SimpleNamespace(type="thinking", thinking="", signature="sig")
    monkeypatch.setattr(fake_anthropic_client, "next_response", FakeResponse([thinking, FakeTextBlock("odpowiedz")]))
    chat = _import_chat()

    assert chat(system="s", user="u") == "odpowiedz"


def test_refusal_without_text_is_an_error_with_its_category(fake_anthropic_client, monkeypatch):
    refusal = FakeResponse([], stop_reason="refusal", stop_details=types.SimpleNamespace(category="bio"))
    monkeypatch.setattr(fake_anthropic_client, "next_response", refusal)
    chat = _import_chat()

    with pytest.raises(RuntimeError, match="odmowil.*bio"):
        chat(system="s", user="u")


def test_stream_refusal_without_text_is_an_error(fake_anthropic_client, monkeypatch):
    monkeypatch.setattr(fake_anthropic_client, "next_stream_texts", ())
    monkeypatch.setattr(fake_anthropic_client, "next_stream_stop", "refusal")
    stream_chat = _import_stream_chat()

    with pytest.raises(RuntimeError, match="odmowil.*cyber"):
        list(stream_chat(system="s", user="u"))
