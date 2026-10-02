"""Statystyki wywolan modelu w pamieci procesu - do diagnostyki w panelu
administratora. Backend chodzi na jednym workerze, wiec jeden obiekt
LLM_STATS widzi wszystkie wywolania; po restarcie liczniki zaczynaja od zera.

Zapis jest w jednym miejscu: llm/generate.py (answer i stream_answer).
Blokada chroni przed rownoleglymi zapisami z puli watkow.
"""

from __future__ import annotations

import math
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

# Ile ostatnich wywolan bierzemy do sredniej i p95.
DEFAULT_WINDOW = 200
MAX_ERROR_LENGTH = 300
# Zmienne env, ktorych wartosci nie moga trafic do komunikatu bledu.
_SECRET_SUFFIXES = ("_API_KEY", "_SECRET", "_TOKEN", "_TOKEN_SECRET", "_COOKIE")
_MIN_SECRET_LENGTH = 6
_REDACTED = "***"
# scheme://uzytkownik:haslo@host -> scheme://***@host
_URL_CREDENTIALS = re.compile(r"(\b[a-zA-Z][\w+.-]*://)[^\s/@:]+:[^\s/@]+@")
# "Bearer <token>" w naglowkach i komunikatach
_BEARER_TOKEN = re.compile(r"(?i)(\bbearer\s+)[\w.~+/=-]+")


@dataclass(frozen=True)
class LlmStatsSnapshot:
    started_at: datetime
    uptime_seconds: float
    total_calls: int
    total_errors: int
    recent_calls: int
    recent_errors: int
    # z udanych wywolan w oknie; None = brak danych
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    last_error: str | None
    last_error_at: datetime | None


def _redact(message: str) -> str:
    """Usuwa z tekstu wartosci kluczy API i innych sekretow z env, dane
    logowania w URL-ach i tokeny Bearer."""
    for name, value in os.environ.items():
        if name.upper().endswith(_SECRET_SUFFIXES) and len(value) >= _MIN_SECRET_LENGTH:
            message = message.replace(value, _REDACTED)
    message = _URL_CREDENTIALS.sub(lambda match: f"{match.group(1)}{_REDACTED}@", message)
    return _BEARER_TOKEN.sub(lambda match: f"{match.group(1)}{_REDACTED}", message)


def describe_error(error: BaseException) -> str:
    """Typ i tresc bledu, bez sekretow, skrocone do MAX_ERROR_LENGTH."""
    text = _redact(f"{type(error).__name__}: {error}")
    return text if len(text) <= MAX_ERROR_LENGTH else text[: MAX_ERROR_LENGTH - 1] + "…"


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Percentyl metoda najblizszej rangi (wartosci posortowane rosnaco)."""
    rank = max(1, math.ceil(fraction * len(sorted_values)))
    return sorted_values[rank - 1]


class LlmStats:
    """Liczniki od startu i okno ostatnich `window` wywolan (czas, sukces)."""

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self._lock = threading.Lock()
        self._recent: deque[tuple[float, bool]] = deque(maxlen=window)
        self._total_calls = 0
        self._total_errors = 0
        self._last_error: str | None = None
        self._last_error_at: datetime | None = None
        self._started_at = datetime.now(timezone.utc)
        self._started_monotonic = time.monotonic()

    def record_success(self, seconds: float) -> None:
        with self._lock:
            self._total_calls += 1
            self._recent.append((seconds, True))

    def record_error(self, seconds: float, error: BaseException) -> None:
        description = describe_error(error)
        with self._lock:
            self._total_calls += 1
            self._total_errors += 1
            self._recent.append((seconds, False))
            self._last_error = description
            self._last_error_at = datetime.now(timezone.utc)

    def snapshot(self) -> LlmStatsSnapshot:
        with self._lock:
            recent = list(self._recent)
            total_calls, total_errors = self._total_calls, self._total_errors
            last_error, last_error_at = self._last_error, self._last_error_at
        latencies = sorted(seconds * 1000 for seconds, ok in recent if ok)
        return LlmStatsSnapshot(
            started_at=self._started_at,
            uptime_seconds=time.monotonic() - self._started_monotonic,
            total_calls=total_calls,
            total_errors=total_errors,
            recent_calls=len(recent),
            recent_errors=sum(1 for _, ok in recent if not ok),
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else None,
            p95_latency_ms=_percentile(latencies, 0.95) if latencies else None,
            last_error=last_error,
            last_error_at=last_error_at,
        )


# Jeden obiekt na proces; testy podmieniaja go przez monkeypatch.
LLM_STATS = LlmStats()


def current_stats() -> LlmStats:
    """Biezacy obiekt statystyk (czytany przy kazdym uzyciu - podmiana w testach dziala)."""
    return LLM_STATS
