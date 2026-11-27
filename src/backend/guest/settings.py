"""Ustawienia wersji testowej bez konta (tryb goscia) z env.

Gosc to osoba, ktora na ekranie logowania wybrala "Kontynuuj bez konta":
dostaje zwykly czat z limitem pytan na cala sesje. Limity chronia budzet
modelu, bo nowa sesje goscia da sie zalozyc w kazdym oknie prywatnym:

    GUEST_MODE                     on/off, domyslnie on
    GUEST_QUESTION_LIMIT           pytania na sesje goscia (domyslnie 2)
    GUEST_SESSION_HOURS            dlugosc sesji; po niej gosc i jego rozmowy
                                   sa kasowane (domyslnie 24)
    GUEST_SESSIONS_PER_IP_PER_DAY  nowe sesje z jednego adresu IP na dobe
                                   (domyslnie 5)
    GUEST_DAILY_TOTAL_LIMIT        pytania wszystkich gosci razem na dobe
                                   (domyslnie 300)
    GUEST_ATTACHMENT_LIMIT         pliki na sesje goscia, 0 = bez zalacznikow
                                   (domyslnie 4)

Bledna wartosc zatrzymuje start backendu (GuestConfigError).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

_TRUE: Final = frozenset({"1", "true", "yes", "on", "tak"})
_FALSE: Final = frozenset({"0", "false", "no", "off", "nie"})

DEFAULT_QUESTION_LIMIT: Final = 2
DEFAULT_SESSION_HOURS: Final = 24
DEFAULT_SESSIONS_PER_IP_PER_DAY: Final = 5
DEFAULT_DAILY_TOTAL_LIMIT: Final = 300
DEFAULT_ATTACHMENT_LIMIT: Final = 4
# rozmiar pliku goscia w MB (mniejszy z tego i limitu z panelu) - stala, nie env
GUEST_MAX_FILE_MB: Final = 5
# gorne granice chronia przed literowka (np. dodatkowe zero)
MAX_QUESTION_LIMIT: Final = 100
MAX_SESSION_HOURS: Final = 24 * 7
MAX_SESSIONS_PER_IP: Final = 1000
MAX_DAILY_TOTAL: Final = 100_000
MAX_ATTACHMENT_LIMIT: Final = 50


class GuestConfigError(ValueError):
    """Bledna wartosc zmiennej GUEST_* - backend nie startuje."""


@dataclass(frozen=True)
class GuestSettings:
    enabled: bool
    question_limit: int
    session_hours: int
    sessions_per_ip_per_day: int
    daily_total_limit: int
    attachment_limit: int

    @property
    def session_seconds(self) -> int:
        return self.session_hours * 3600


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise GuestConfigError(f"{name} musi byc on/off (jest: {raw!r})")


def _int(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise GuestConfigError(f"{name} musi byc liczba calkowita (jest: {raw!r})") from None
    if not minimum <= value <= maximum:
        raise GuestConfigError(f"{name} musi byc w zakresie {minimum}..{maximum} (jest: {value})")
    return value


def load_guest_settings(env: Mapping[str, str]) -> GuestSettings:
    """Ustawienia gosci z `env`.

    Raises:
        GuestConfigError: zla wartosc ktorejs zmiennej GUEST_*.
    """
    return GuestSettings(
        enabled=_flag(env, "GUEST_MODE", True),
        question_limit=_int(env, "GUEST_QUESTION_LIMIT", DEFAULT_QUESTION_LIMIT, 1, MAX_QUESTION_LIMIT),
        session_hours=_int(env, "GUEST_SESSION_HOURS", DEFAULT_SESSION_HOURS, 1, MAX_SESSION_HOURS),
        sessions_per_ip_per_day=_int(
            env, "GUEST_SESSIONS_PER_IP_PER_DAY", DEFAULT_SESSIONS_PER_IP_PER_DAY, 1, MAX_SESSIONS_PER_IP
        ),
        daily_total_limit=_int(env, "GUEST_DAILY_TOTAL_LIMIT", DEFAULT_DAILY_TOTAL_LIMIT, 1, MAX_DAILY_TOTAL),
        attachment_limit=_int(env, "GUEST_ATTACHMENT_LIMIT", DEFAULT_ATTACHMENT_LIMIT, 0, MAX_ATTACHMENT_LIMIT),
    )


@lru_cache(maxsize=1)
def get_guest_settings() -> GuestSettings:
    """Ustawienia z os.environ, liczone raz na proces (dependency FastAPI)."""
    return load_guest_settings(os.environ)
