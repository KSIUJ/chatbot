"""Konfiguracja motywow okazjonalnych z env.

OCCASION_SOURCE_URL     strona glowna KSI, z ktorej czytamy aktywny motyw
                        (domyslnie https://ksi.sh/); off/false/0/no/nie wylacza
OCCASION_REFRESH_SECONDS co ile sekund sprawdzac strone (15-3600, domyslnie 60)
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

DEFAULT_SOURCE_URL = "https://ksi.sh/"
DEFAULT_REFRESH_SECONDS = 60
MIN_REFRESH_SECONDS = 15
MAX_REFRESH_SECONDS = 3600
_OFF_VALUES = frozenset({"off", "false", "0", "no", "nie"})


class OccasionConfigError(RuntimeError):
    """Bledna wartosc OCCASION_* w env."""


@dataclass(frozen=True)
class OccasionSettings:
    # None = funkcja wylaczona (czat zawsze w zwyklym wygladzie)
    source_url: str | None
    refresh_seconds: int


def _source_url(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return DEFAULT_SOURCE_URL
    if value.lower() in _OFF_VALUES:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise OccasionConfigError(f"OCCASION_SOURCE_URL musi byc adresem http(s), jest {value!r}")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise OccasionConfigError("OCCASION_SOURCE_URL nie moze miec loginu, zapytania ani fragmentu")
    return value


def _refresh_seconds(raw: str) -> int:
    value = raw.strip()
    if not value:
        return DEFAULT_REFRESH_SECONDS
    try:
        seconds = int(value)
    except ValueError:
        raise OccasionConfigError(f"OCCASION_REFRESH_SECONDS musi byc liczba, jest {value!r}") from None
    if not MIN_REFRESH_SECONDS <= seconds <= MAX_REFRESH_SECONDS:
        raise OccasionConfigError(
            f"OCCASION_REFRESH_SECONDS musi byc w zakresie {MIN_REFRESH_SECONDS}-{MAX_REFRESH_SECONDS}"
        )
    return seconds


def load_occasion_settings(env: Mapping[str, str]) -> OccasionSettings:
    """Czyta ustawienia motywow okazjonalnych.

    Raises:
        OccasionConfigError: zly adres strony albo odstep odswiezania.
    """
    return OccasionSettings(
        source_url=_source_url(env.get("OCCASION_SOURCE_URL") or ""),
        refresh_seconds=_refresh_seconds(env.get("OCCASION_REFRESH_SECONDS") or ""),
    )


@lru_cache(maxsize=1)
def get_occasion_settings() -> OccasionSettings:
    """Ustawienia z os.environ (sprawdzane przy starcie aplikacji)."""
    return load_occasion_settings(os.environ)
