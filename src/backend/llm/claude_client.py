"""
Klient Claude API (Anthropic) - alternatywa dla lokalnego Ollamy (client.py),
uzywana gdy LLM_PROVIDER=claude (patrz generate.py). Ten sam interfejs
chat(system, user) -> str co client.py, zeby generate.py mogl przelaczac
providera bez zmian w logice RAG.
"""

import os

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 4096


def chat(
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = 300,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    import anthropic

    model = model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)
    client = anthropic.Anthropic(timeout=timeout)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
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
