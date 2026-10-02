"""Odczyt konfiguracji warstwy LLM z env: wybrany dostawca i pojedyncze ustawienia."""

import os

OLLAMA = "ollama"
PROVIDERS = (OLLAMA, "claude", "cursor", "openrouter")


def env_setting(name: str, default: str) -> str:
    """Wartosc zmiennej env bez bialych znakow; pusta lub brak -> default."""
    return os.getenv(name, "").strip() or default


def current_provider() -> str:
    """Dostawca z LLM_PROVIDER (bez rozrozniania wielkosci liter).

    Brak zmiennej lub nieznana wartosc -> "ollama".
    """
    provider = env_setting("LLM_PROVIDER", OLLAMA).lower()
    return provider if provider in PROVIDERS else OLLAMA


# Dostawcy, ktorym przekazujemy obrazy z zalacznikow. Cursor (jedno pole
# tekstowe) nie przyjmuje obrazow. Model wybrany w OpenRouter/Ollamie moze ich
# nie obslugiwac - wtedy blad API konczy sie zwyklym llm_failed.
VISION_PROVIDERS = frozenset({OLLAMA, "claude", "openrouter"})


def provider_supports_images(provider: str | None = None) -> bool:
    """Czy dostawca (domyslnie biezacy) przyjmuje obrazy."""
    return (provider or current_provider()) in VISION_PROVIDERS
