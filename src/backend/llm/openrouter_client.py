"""
Klient OpenRouter API, uzywany gdy LLM_PROVIDER=openrouter. Ten sam interfejs
chat(system, user, history=None) -> str i stream_chat(...) -> kawalki tekstu
co ollama_client.py.

OpenRouter wystawia API zgodne z chat completions OpenAI i routuje zapytanie
do wybranego dostawcy, wiec model zmienia sie sama zmienna OPENROUTER_MODEL.
Klient uzywa requests (bez SDK openai).
"""

import json
from collections.abc import Iterator, Sequence

from .http_api import BearerApi, build_messages
from .images import ImageInput
from .provider import env_setting

DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_TIMEOUT = 300

_API = BearerApi(
    base_url="https://openrouter.ai/api/v1",
    label="OpenRouter",
    key_env="OPENROUTER_API_KEY",
    missing_key_message=(
        "Brak klucza OpenRouter (OPENROUTER_API_KEY). Wygeneruj go w "
        "https://openrouter.ai/keys i ustaw w .env."
    ),
    status_messages={
        401: "Nieprawidlowy lub brakujacy klucz OpenRouter (OPENROUTER_API_KEY).",
        402: "Brak srodkow na koncie OpenRouter albo model przekracza limit kredytow.",
        429: "Przekroczono limit zapytan do OpenRouter.",
    },
)


def _messages(
    system: str, user: str, history: list[dict[str, str]] | None, images: Sequence[ImageInput] | None
) -> list[dict[str, object]]:
    """Wiadomosci chat completions; z obrazami pytanie ma czesci: tekst
    i obrazy jako adresy data: (format OpenAI, ktory OpenRouter przekazuje
    dalej). Model bez obslugi obrazow zwroci blad API (-> llm_failed)."""
    messages = build_messages(system, user, history)
    if images:
        parts: list[dict[str, object]] = [{"type": "text", "text": user}]
        parts.extend({"type": "image_url", "image_url": {"url": image.data_url()}} for image in images)
        messages[-1] = {"role": "user", "content": parts}
    return messages


def chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = DEFAULT_TIMEOUT,
    images: Sequence[ImageInput] | None = None,
) -> str:
    """Wysyla rozmowe do OpenRouter i zwraca tekst pierwszego wyboru."""
    model = model or env_setting("OPENROUTER_MODEL", DEFAULT_MODEL)

    payload = {
        "model": model,
        "messages": _messages(system, user, history, images),
        "temperature": temperature,
        "stream": False,
    }
    data = _API.request("POST", "/chat/completions", timeout=timeout, json=payload)

    # OpenRouter potrafi odpowiedziec HTTP 200 z bledem w ciele (np. gdy padnie
    # dostawca, do ktorego routuje zapytanie) - wtedy nie ma klucza "choices".
    _raise_on_error(data)

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter zwrocil odpowiedz bez zadnego wyboru (choices).")

    return (choices[0].get("message", {}).get("content") or "").strip()


def stream_chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = DEFAULT_TIMEOUT,
    images: Sequence[ImageInput] | None = None,
) -> Iterator[str]:
    """Jak chat(), ale oddaje kawalki odpowiedzi na biezaco (SSE z OpenRouter).
    Zamkniecie generatora zamyka polaczenie."""
    payload = {
        "model": model or env_setting("OPENROUTER_MODEL", DEFAULT_MODEL),
        "messages": _messages(system, user, history, images),
        "temperature": temperature,
        "stream": True,
    }
    with _API.stream("POST", "/chat/completions", timeout=timeout, json=payload) as response:
        for raw in response.iter_lines():
            # linie zaczynajace sie od ":" to komentarze podtrzymujace polaczenie
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                return
            event = json.loads(data)
            # blad w trakcie odpowiedzi przychodzi jako zwykle zdarzenie z "error"
            _raise_on_error(event)
            choices = event.get("choices") or []
            text = (choices[0].get("delta") or {}).get("content") if choices else None
            if text:
                yield text


def _raise_on_error(data: dict) -> None:
    error = data.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"Blad OpenRouter: {message}")
