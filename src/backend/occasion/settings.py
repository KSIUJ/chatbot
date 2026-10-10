"""Konfiguracja motywow okazjonalnych z env.

OCCASION_SOURCE_URL     strona glowna KSI, z ktorej czytamy aktywny motyw
                        (domyslnie https://ksi.sh/); off/false/0/no/nie wylacza
OCCASION_REFRESH_SECONDS co ile sekund sprawdzac strone (15-3600, domyslnie 60)
OCCASION_API_TOKEN      token API ksi.sh (/api/occasion na hoscie strony): ktora
                        okazja trwa i kiedy sie konczy. Bez niego (albo gdy API
                        nie odpowiada) - sama strona glowna. Sekret: tylko w .env.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit

DEFAULT_SOURCE_URL = "https://ksi.sh/"
DEFAULT_REFRESH_SECONDS = 60
MIN_REFRESH_SECONDS = 15
MAX_REFRESH_SECONDS = 3600
_OFF_VALUES = frozenset({"off", "false", "0", "no", "nie"})
# znaki tokenu Bearer (RFC 6750) - nic, co rozbiloby naglowek
_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{16,512}")


class OccasionConfigError(RuntimeError):
    """Bledna wartosc OCCASION_* w env."""


@dataclass(frozen=True)
class OccasionSettings:
    # None = funkcja wylaczona (czat zawsze w zwyklym wygladzie)
    source_url: str | None
    refresh_seconds: int
    # None = bez API; repr=False: token nie trafia do logow ani komunikatow
    api_token: str | None = field(default=None, repr=False)


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


def _api_token(raw: str, source_url: str | None) -> str | None:
    value = raw.strip()
    if not value or source_url is None:
        return None
    if _TOKEN.fullmatch(value) is None:
        raise OccasionConfigError("OCCASION_API_TOKEN ma niedozwolone znaki albo dlugosc")
    if not source_url.startswith("https://"):
        raise OccasionConfigError("OCCASION_API_TOKEN wymaga OCCASION_SOURCE_URL po https")
    return value


def load_occasion_settings(env: Mapping[str, str]) -> OccasionSettings:
    """Czyta ustawienia motywow okazjonalnych.

    Raises:
        OccasionConfigError: zly adres strony, odstep odswiezania albo token.
    """
    source_url = _source_url(env.get("OCCASION_SOURCE_URL") or "")
    return OccasionSettings(
        source_url=source_url,
        refresh_seconds=_refresh_seconds(env.get("OCCASION_REFRESH_SECONDS") or ""),
        api_token=_api_token(env.get("OCCASION_API_TOKEN") or "", source_url),
    )


@lru_cache(maxsize=1)
def get_occasion_settings() -> OccasionSettings:
    """Ustawienia z os.environ (sprawdzane przy starcie aplikacji)."""
    return load_occasion_settings(os.environ)
