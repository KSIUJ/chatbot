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

import requests

API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_TIMEOUT = 300


def _api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Brak klucza OpenRouter (OPENROUTER_API_KEY). Wygeneruj go w "
            "https://openrouter.ai/keys i ustaw w .env."
        )
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _raise_for_status(response: requests.Response) -> None:
    if response.status_code < 400:
        return
    if response.status_code == 401:
        raise RuntimeError(
            "Nieprawidlowy lub brakujacy klucz OpenRouter (OPENROUTER_API_KEY)."
        )
    if response.status_code == 402:
        raise RuntimeError(
            "Brak srodkow na koncie OpenRouter albo model przekracza limit kredytow."
        )
    if response.status_code == 429:
        raise RuntimeError("Przekroczono limit zapytan do OpenRouter.")
    raise RuntimeError(
        f"Blad OpenRouter (status {response.status_code}): {response.text[:500]}"
    )


def _request(method: str, path: str, *, timeout: float = DEFAULT_TIMEOUT, **kwargs) -> dict:
    try:
        response = requests.request(
            method, f"{API_BASE}{path}", headers=_headers(), timeout=timeout, **kwargs
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Blad polaczenia z OpenRouter: {e}") from e

    _raise_for_status(response)
    return response.json()


def list_models() -> list[str]:
    """Zwraca ID modeli dostepnych przez OpenRouter - pomocne do ustalenia
    poprawnej wartosci OPENROUTER_MODEL."""
    data = _request("GET", "/models")
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

    messages = [{"role": "system", "content": system}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    data = _request("POST", "/chat/completions", timeout=timeout, json=payload)

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
