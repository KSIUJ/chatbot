"""Klient lokalnego Ollamy (POST /api/chat), domyslny dostawca (LLM_PROVIDER=ollama)."""

import requests

from .http_api import build_messages
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
) -> str:
    """Wysyla rozmowe do Ollamy i zwraca tekst odpowiedzi."""
    model = model or env_setting("OLLAMA_MODEL", DEFAULT_MODEL)
    host = host or env_setting("OLLAMA_HOST", DEFAULT_HOST)
    num_ctx = num_ctx or int(env_setting("OLLAMA_NUM_CTX", str(DEFAULT_NUM_CTX)))

    response = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": build_messages(system, user, history),
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]
