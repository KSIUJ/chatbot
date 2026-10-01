"""
Klient Claude API (Anthropic), uzywany gdy LLM_PROVIDER=claude. Ten sam
interfejs chat(system, user, history=None) -> str co ollama_client.py.
"""

from .provider import env_setting

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 4096
API_KEY_ENV = "ANTHROPIC_API_KEY"


def chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = 300,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Wysyla rozmowe do Claude API i zwraca polaczony tekst odpowiedzi."""
    api_key = env_setting(API_KEY_ENV, "")
    if not api_key:
        raise RuntimeError(
            "Brak klucza Claude API (ANTHROPIC_API_KEY). Ustaw go w .env."
        )

    import anthropic

    model = model or env_setting("CLAUDE_MODEL", DEFAULT_MODEL)
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)

    # Claude API przyjmuje historie jako natywne messages przed biezacym pytaniem.
    messages = [*(history or []), {"role": "user", "content": user}]

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
    except anthropic.AuthenticationError as e:
        raise RuntimeError(
            "Nieprawidlowy lub brakujacy klucz Claude API (ANTHROPIC_API_KEY)."
        ) from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Przekroczono limit zapytan do Claude API.") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError("Blad polaczenia z Claude API.") from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Blad Claude API (status {e.status_code}).") from e

    return "".join(block.text for block in response.content if block.type == "text")
