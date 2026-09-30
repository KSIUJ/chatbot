"""
Klient OpenRouter API - alternatywa dla lokalnego Ollamy (client.py), Claude
API (claude_client.py) i Cursor Cloud Agents (cursor_client.py), uzywana gdy
LLM_PROVIDER=openrouter (patrz generate.py). Ten sam interfejs
chat(system, user, history=None) -> str, zeby generate.py mogl przelaczac
providera bez zmian w logice RAG.

OpenRouter wystawia jedno API zgodne z formatem chat completions OpenAI i
routuje zapytanie do wybranego dostawcy (Anthropic, Google, Meta, Qwen...),
wiec model podmienia sie sama zmienna OPENROUTER_MODEL - bez zmian w kodzie.
Pelna lista ID: GET https://openrouter.ai/api/v1/models (bez klucza) albo
list_models() ponizej.

Uzywamy biblioteki requests (jak cursor_client.py) zamiast SDK openai, zeby
nie dokladac nowej zaleznosci.
"""

import os

from .http_api import BearerApi, build_messages

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


def list_models() -> list[str]:
    """Zwraca ID modeli dostepnych przez OpenRouter - pomocne do ustalenia
    poprawnej wartosci OPENROUTER_MODEL."""
    data = _API.request("GET", "/models", timeout=DEFAULT_TIMEOUT)
    return [item["id"] for item in data.get("data", [])]


def chat(
    system: str,
    user: str,
    history: list[dict] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    # Puste OPENROUTER_MODEL= w .env to nie to samo co brak zmiennej: getenv
    # zwraca wtedy "" i bez tego trafiloby ono do API jako nazwa modelu.
    model = model or os.getenv("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL

    messages = build_messages(system, user, history)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    data = _API.request("POST", "/chat/completions", timeout=timeout, json=payload)

    # OpenRouter potrafi odpowiedziec HTTP 200 z bledem w ciele (np. gdy padnie
    # dostawca, do ktorego routuje zapytanie) - wtedy nie ma klucza "choices".
    error = data.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"Blad OpenRouter: {message}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter zwrocil odpowiedz bez zadnego wyboru (choices).")

    return (choices[0].get("message", {}).get("content") or "").strip()
