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
