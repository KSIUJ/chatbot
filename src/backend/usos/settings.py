"""Konfiguracja polaczenia kont z USOS (OAuth 1.0a, USOS API UJ) z env.

USOS_CONNECT          on/off - wlacznik funkcji (domyslnie off). Klucz aplikacji
                      jest wspolny ze scraperem (pipeline/scrapers/usos), wiec
                      sam klucz w .env nie moze jej wlaczac.
USOS_CONSUMER_KEY     klucz aplikacji USOS API; pusty = funkcja niedostepna
USOS_CONSUMER_SECRET  sekret aplikacji (wymagany razem z kluczem)
USOS_SCOPES           uprawnienia rozdzielone "|" (studies|grades|crstests|student_exams|offline_access)
USOS_CALLBACK_URL     adres powrotu z USOS (domyslnie z OIDC_REDIRECT_URI:
                      .../api/auth/callback -> .../api/usos/callback)
USOS_HTTP_TIMEOUT     timeout zapytan do USOS API w sekundach (10)
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from ..auth.settings import AuthSettings, get_auth_settings

BASE_URL = "https://apps.usos.uj.edu.pl/"
DEFAULT_SCOPES = "studies|grades|crstests|student_exams|offline_access"
DEFAULT_HTTP_TIMEOUT = 10.0
# Czas na zgode w USOS (ciasteczko z request tokenem); request token USOS i tak
# wygasa po kilku minutach.
CONNECT_STATE_MAX_AGE_SECONDS = 600
CALLBACK_PATH = "/api/usos/callback"
_AUTH_CALLBACK_SUFFIX = "/auth/callback"

_TRUE = frozenset({"1", "true", "yes", "on", "tak"})
_FALSE = frozenset({"0", "false", "no", "off", "nie"})
_SCOPE = re.compile(r"[a-z_]{1,64}")
# klucz aplikacji USOS to znaki alfanumeryczne - nic, co rozbiloby naglowek
_CONSUMER = re.compile(r"[A-Za-z0-9]{8,128}")


class UsosConfigError(RuntimeError):
    """Bledna wartosc USOS_* w env."""


@dataclass(frozen=True)
class UsosSettings:
    """Zwalidowana konfiguracja. available=False: endpointy /usos/* odpowiadaja
    503 usos_unavailable, a /usos/status mowi available: false."""

    available: bool
    # repr=False: klucz i sekret nie trafiaja do logow ani komunikatow
    consumer_key: str = field(repr=False)
    consumer_secret: str = field(repr=False)
    scopes: str
    callback_url: str
    http_timeout_seconds: float
    base_url: str = BASE_URL
    connect_state_max_age_seconds: int = CONNECT_STATE_MAX_AGE_SECONDS

    @property
    def scope_list(self) -> list[str]:
        return self.scopes.split("|") if self.scopes else []


def _derived_callback_url(redirect_uri: str) -> str:
    """Adres powrotu obok callbacku logowania: ta sama sciezka z usos zamiast
    auth (.../api/auth/callback -> .../api/usos/callback)."""
    parts = urlsplit(redirect_uri)
    path = parts.path.rstrip("/")
    if path.endswith(_AUTH_CALLBACK_SUFFIX):
        path = path[: -len(_AUTH_CALLBACK_SUFFIX)] + "/usos/callback"
    else:
        path = CALLBACK_PATH
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _parse_scopes(raw: str, errors: list[str]) -> str:
    value = raw.strip() or DEFAULT_SCOPES
    scopes = [s.strip() for s in value.split("|") if s.strip()]
    bad = [s for s in scopes if not _SCOPE.fullmatch(s)]
    if bad or not scopes:
        errors.append("USOS_SCOPES musi byc lista kluczy rozdzielonych | (np. studies|grades)")
    return "|".join(dict.fromkeys(scopes))


def load_usos_settings(env: Mapping[str, str], auth: AuthSettings) -> UsosSettings:
    """Buduje UsosSettings z mapy zmiennych srodowiskowych.

    Args:
        env: zrodlo zmiennych, zwykle os.environ (w testach zwykly dict).
        auth: konfiguracja logowania - z niej domyslny adres powrotu.

    Raises:
        UsosConfigError: z lista wszystkich problemow naraz.
    """
    errors: list[str] = []

    def get(name: str) -> str:
        return (env.get(name) or "").strip()

    enabled_raw = get("USOS_CONNECT").lower()
    if not enabled_raw or enabled_raw in _FALSE:
        enabled = False
    elif enabled_raw in _TRUE:
        enabled = True
    else:
        errors.append("USOS_CONNECT musi byc on/off")
        enabled = False

    key = get("USOS_CONSUMER_KEY")
    secret = get("USOS_CONSUMER_SECRET")
    # klucz sprawdzamy tylko przy wlaczonej funkcji - uzywa go tez scraper
    # i jego konfiguracja nie moze zatrzymac startu backendu
    if enabled and key and not _CONSUMER.fullmatch(key):
        errors.append("USOS_CONSUMER_KEY ma niedozwolone znaki albo dlugosc")
    if enabled and key and not secret:
        errors.append("USOS_CONSUMER_SECRET jest wymagane razem z USOS_CONSUMER_KEY")

    scopes = _parse_scopes(get("USOS_SCOPES"), errors)

    callback_url = get("USOS_CALLBACK_URL") or _derived_callback_url(auth.redirect_uri)
    parts = urlsplit(callback_url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        errors.append("USOS_CALLBACK_URL musi byc pelnym adresem http(s)://.../api/usos/callback bez zapytania")
    elif parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
        errors.append("USOS_CALLBACK_URL musi byc adresem https:// (http tylko dla localhost)")

    timeout_raw = get("USOS_HTTP_TIMEOUT")
    timeout = DEFAULT_HTTP_TIMEOUT
    if timeout_raw:
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = math.nan
        if not math.isfinite(timeout) or timeout <= 0:
            errors.append(f"USOS_HTTP_TIMEOUT musi byc dodatnia liczba, jest {timeout_raw!r}")
            timeout = DEFAULT_HTTP_TIMEOUT

    if errors:
        raise UsosConfigError("Bledna konfiguracja USOS (patrz .env.example):\n- " + "\n- ".join(errors))

    return UsosSettings(
        available=enabled and bool(key and secret),
        consumer_key=key,
        consumer_secret=secret,
        scopes=scopes,
        callback_url=callback_url,
        http_timeout_seconds=timeout,
    )


@lru_cache(maxsize=1)
def get_usos_settings() -> UsosSettings:
    """Konfiguracja z os.environ, liczona raz na proces. Dependency FastAPI -
    testy podmieniaja ja przez app.dependency_overrides albo cache_clear()."""
    return load_usos_settings(os.environ, get_auth_settings())
