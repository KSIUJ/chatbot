"""
Klient Claude API (Anthropic), uzywany gdy LLM_PROVIDER=claude. Ten sam
interfejs chat(system, user, history=None) -> str i stream_chat(...) ->
kawalki tekstu co ollama_client.py.

Domyslnie Claude Haiku 5.5: mysli adaptacyjnie (bloki thinking sa pomijane -
oddajemy tylko tekst), glebokosc ustawia CLAUDE_EFFORT (output_config.effort),
a temperature/top_p sa niedozwolone (400), wiec ich nie wysylamy.
"""

from collections.abc import Iterator, Sequence
from types import ModuleType
from typing import TYPE_CHECKING

from .images import ImageInput
from .provider import env_setting

if TYPE_CHECKING:
    from anthropic import Anthropic

DEFAULT_MODEL = "claude-haiku-5-5"
# myslenie liczy sie do max_tokens - zapas na nie i na odpowiedz
DEFAULT_MAX_TOKENS = 16000
API_KEY_ENV = "ANTHROPIC_API_KEY"
# low | medium | high | xhigh | max; "off" = bez output_config (modele bez effort)
EFFORT_ENV = "CLAUDE_EFFORT"
DEFAULT_EFFORT = "medium"
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
EFFORT_OFF = ("off", "none", "0")


def _client(timeout: int) -> tuple[ModuleType, "Anthropic"]:
    """Modul anthropic i klient z kluczem z env (bez klucza - RuntimeError)."""
    api_key = env_setting(API_KEY_ENV, "")
    if not api_key:
        raise RuntimeError(
            "Brak klucza Claude API (ANTHROPIC_API_KEY). Ustaw go w .env."
        )

    import anthropic

    return anthropic, anthropic.Anthropic(api_key=api_key, timeout=timeout)


def _user_content(user: str, images: Sequence[ImageInput] | None) -> str | list[dict[str, object]]:
    """Tresc pytania: sam tekst albo bloki obrazow (base64) i na koncu tekst."""
    if not images:
        return user
    blocks: list[dict[str, object]] = [
        {"type": "image", "source": {"type": "base64", "media_type": image.mime, "data": image.base64()}}
        for image in images
    ]
    blocks.append({"type": "text", "text": user})
    return blocks


def _effort() -> str | None:
    """Poziom effort z CLAUDE_EFFORT; None = nie wysylac (np. Haiku 4.5, ktory go nie zna)."""
    value = env_setting(EFFORT_ENV, DEFAULT_EFFORT).strip().lower()
    if value in EFFORT_OFF:
        return None
    if value not in EFFORT_LEVELS:
        raise RuntimeError(f"{EFFORT_ENV} musi byc jednym z: {', '.join(EFFORT_LEVELS)} albo off")
    return value


def _request(
    system: str, user: str, history: list[dict[str, str]] | None, model: str | None,
    max_tokens: int, images: Sequence[ImageInput] | None = None,
) -> dict:
    # Claude API przyjmuje historie jako natywne messages przed biezacym pytaniem.
    request: dict[str, object] = {
        "model": model or env_setting("CLAUDE_MODEL", DEFAULT_MODEL),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [*(history or []), {"role": "user", "content": _user_content(user, images)}],
    }
    effort = _effort()
    if effort is not None:
        request["output_config"] = {"effort": effort}
    return request


def _refused(stop_reason: str | None, stop_details: object) -> RuntimeError:
    """Odmowa klasyfikatorow bezpieczenstwa (stop_reason "refusal") bez tekstu -
    blad z kategoria do logu zamiast pustej odpowiedzi."""
    category = getattr(stop_details, "category", None) or "brak kategorii"
    return RuntimeError(f"Claude API odmowil odpowiedzi ({stop_reason}, {category}).")


def _translate_error(anthropic: ModuleType, error: Exception) -> RuntimeError | None:
    """Czytelny RuntimeError dla bledow API; None dla innych wyjatkow."""
    if isinstance(error, anthropic.AuthenticationError):
        return RuntimeError("Nieprawidlowy lub brakujacy klucz Claude API (ANTHROPIC_API_KEY).")
    if isinstance(error, anthropic.RateLimitError):
        return RuntimeError("Przekroczono limit zapytan do Claude API.")
    if isinstance(error, anthropic.APIConnectionError):
        return RuntimeError("Blad polaczenia z Claude API.")
    if isinstance(error, anthropic.APIStatusError):
        return RuntimeError(f"Blad Claude API (status {error.status_code}).")
    return None


def chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    timeout: int = 300,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    images: Sequence[ImageInput] | None = None,
) -> str:
    """Wysyla rozmowe do Claude API i zwraca polaczony tekst odpowiedzi.
    images - obrazy z zalacznikow, dolaczane do biezacego pytania."""
    anthropic, client = _client(timeout)
    request = _request(system, user, history, model, max_tokens, images)
    try:
        response = client.messages.create(**request)
    except Exception as e:
        translated = _translate_error(anthropic, e)
        if translated is None:
            raise
        raise translated from e

    text = "".join(block.text for block in response.content if block.type == "text")
    if not text and getattr(response, "stop_reason", None) == "refusal":
        raise _refused(response.stop_reason, getattr(response, "stop_details", None))
    return text


def stream_chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    timeout: int = 300,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    images: Sequence[ImageInput] | None = None,
) -> Iterator[str]:
    """Jak chat(), ale oddaje kawalki tekstu na biezaco (messages.stream).
    Zamkniecie generatora zamyka strumien i polaczenie."""
    anthropic, client = _client(timeout)
    try:
        request = _request(system, user, history, model, max_tokens, images)
        with client.messages.stream(**request) as stream:
            produced = False
            for text in stream.text_stream:
                produced = produced or bool(text)
                yield text
            if not produced:
                final = stream.get_final_message()
                if final.stop_reason == "refusal":
                    raise _refused(final.stop_reason, getattr(final, "stop_details", None))
    except Exception as e:
        translated = _translate_error(anthropic, e)
        if translated is None:
            raise
        raise translated from e
