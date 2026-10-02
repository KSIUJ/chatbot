"""Klient lokalnego Ollamy (POST /api/chat), domyslny dostawca (LLM_PROVIDER=ollama)."""

import json
from collections.abc import Iterator, Sequence

import requests

from .http_api import build_messages
from .images import ImageInput
from .provider import env_setting

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:14b"
DEFAULT_NUM_CTX = 8192


def chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    host: str | None = None,
    temperature: float = 0.2,
    timeout: int = 300,
    num_ctx: int | None = None,
    images: Sequence[ImageInput] | None = None,
) -> str:
    """Wysyla rozmowe do Ollamy i zwraca tekst odpowiedzi."""
    url, payload = _request(system, user, history, model, host, temperature, num_ctx, stream=False, images=images)
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()["message"]["content"]


def stream_chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    host: str | None = None,
    temperature: float = 0.2,
    timeout: int = 300,
    num_ctx: int | None = None,
    images: Sequence[ImageInput] | None = None,
) -> Iterator[str]:
    """Jak chat(), ale oddaje kawalki odpowiedzi na biezaco (NDJSON z Ollamy).
    Zamkniecie generatora zamyka polaczenie, wiec Ollama przestaje generowac."""
    url, payload = _request(system, user, history, model, host, temperature, num_ctx, stream=True, images=images)
    with requests.post(url, json=payload, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("error"):
                raise RuntimeError(f"Blad Ollamy: {data['error']}")
            text = (data.get("message") or {}).get("content") or ""
            if text:
                yield text
            if data.get("done"):
                return


def _request(
    system: str,
    user: str,
    history: list[dict[str, str]] | None,
    model: str | None,
    host: str | None,
    temperature: float,
    num_ctx: int | None,
    *,
    stream: bool,
    images: Sequence[ImageInput] | None = None,
) -> tuple[str, dict]:
    """Adres i cialo POST /api/chat; brakujace ustawienia z env. Obrazy
    trafiaja do pola "images" pytania (base64) - model musi je obslugiwac."""
    model = model or env_setting("OLLAMA_MODEL", DEFAULT_MODEL)
    host = host or env_setting("OLLAMA_HOST", DEFAULT_HOST)
    num_ctx = num_ctx or int(env_setting("OLLAMA_NUM_CTX", str(DEFAULT_NUM_CTX)))
    messages = build_messages(system, user, history)
    if images:
        messages[-1] = {**messages[-1], "images": [image.base64() for image in images]}
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    return f"{host}/api/chat", payload
