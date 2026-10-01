"""
Klient OpenRouter API, uzywany gdy LLM_PROVIDER=openrouter. Ten sam interfejs
chat(system, user, history=None) -> str co ollama_client.py.

OpenRouter wystawia API zgodne z chat completions OpenAI i routuje zapytanie
do wybranego dostawcy, wiec model zmienia sie sama zmienna OPENROUTER_MODEL.
Klient uzywa requests (bez SDK openai).
"""

from .http_api import BearerApi, build_messages
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


def chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Wysyla rozmowe do OpenRouter i zwraca tekst pierwszego wyboru."""
    model = model or env_setting("OPENROUTER_MODEL", DEFAULT_MODEL)

    payload = {
        "model": model,
        "messages": build_messages(system, user, history),
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
