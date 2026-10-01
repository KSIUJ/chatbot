"""
Testy strumieniowania w ollama_client.py. Podmieniamy requests.post na atrape
z odpowiedzia NDJSON (jedna linia JSON na kawalek odpowiedzi), wiec testy nie
wymagaja dzialajacej Ollamy.
"""

import json

import pytest
import requests

from src.backend.llm import ollama_client


def _line(content: str = "", done: bool = False, **extra) -> bytes:
    return json.dumps({"message": {"role": "assistant", "content": content}, "done": done, **extra}).encode()


class FakeStreamResponse:
    def __init__(self, lines: list[bytes], status_code: int = 200):
        self.lines = lines
        self.status_code = status_code
        self.closed = False
        self.read_lines = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def iter_lines(self):
        for line in self.lines:
            self.read_lines += 1
            yield line


@pytest.fixture
def fake_post(monkeypatch):
    calls = []
    holder = {"response": FakeStreamResponse([_line("ok", done=True)])}

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return holder["response"]

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    return calls, holder


def test_stream_chat_yields_content_until_done(fake_post):
    calls, holder = fake_post
    holder["response"] = FakeStreamResponse(
        [_line("Dzie"), b"", _line("kanat "), _line(""), _line("czynny.", done=False), _line(done=True),
         _line("po koncu")]
    )

    chunks = list(ollama_client.stream_chat(system="s", user="u"))

    assert chunks == ["Dzie", "kanat ", "czynny."]
    assert calls[0]["url"].endswith("/api/chat")
    assert calls[0]["json"]["stream"] is True
    assert calls[0]["stream"] is True
    assert calls[0]["json"]["messages"][0] == {"role": "system", "content": "s"}
    assert holder["response"].closed


def test_stream_chat_decodes_polish_characters(fake_post):
    _, holder = fake_post
    holder["response"] = FakeStreamResponse([_line("Pokój ąę"), _line(done=True)])

    assert list(ollama_client.stream_chat(system="s", user="u")) == ["Pokój ąę"]


def test_stream_chat_raises_on_error_line(fake_post):
    _, holder = fake_post
    holder["response"] = FakeStreamResponse([_line("cz"), json.dumps({"error": "model not found"}).encode()])

    stream = ollama_client.stream_chat(system="s", user="u")

    assert next(stream) == "cz"
    with pytest.raises(RuntimeError, match="model not found"):
        next(stream)
    assert holder["response"].closed


def test_stream_chat_raises_on_http_error(fake_post):
    _, holder = fake_post
    holder["response"] = FakeStreamResponse([], status_code=500)

    with pytest.raises(requests.HTTPError):
        list(ollama_client.stream_chat(system="s", user="u"))
    assert holder["response"].closed


def test_closing_stream_early_closes_http_response(fake_post):
    _, holder = fake_post
    holder["response"] = FakeStreamResponse([_line("a"), _line("b"), _line("c"), _line(done=True)])

    stream = ollama_client.stream_chat(system="s", user="u")
    assert next(stream) == "a"
    stream.close()

    assert holder["response"].closed
    assert holder["response"].read_lines == 1
