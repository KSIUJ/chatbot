"""Odstep miedzy zapytaniami i czas ponowienia po bledzie chwilowym - wspolne
dla klientow HTTP scraperow (USOS API, USOSweb)."""

from __future__ import annotations

import time
from collections.abc import Callable

# najdluzsze czekanie przed ponowieniem, takze gdy serwer prosi o wiecej (Retry-After)
MAX_BACKOFF = 300.0


class Throttle:
    """Zapytania nie czesciej niz co `delay` sekund."""

    def __init__(
        self,
        delay: float,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.delay = delay
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    def wait(self) -> None:
        """Czeka, az od poprzedniego zapytania minie `delay` sekund."""
        if self._last is not None:
            left = self.delay - (self._clock() - self._last)
            if left > 0:
                self._sleep(left)
        self._last = self._clock()


def backoff_seconds(attempt: int, retry_after: str | None = None, cap: float = MAX_BACKOFF) -> float:
    """Czas przed ponowieniem numer `attempt` (od 0): 2, 4, 8... s, co najmniej
    liczbowe Retry-After z odpowiedzi, ale nie wiecej niz `cap`."""
    wait = 2.0 * 2**attempt
    value = (retry_after or "").strip()
    if value.isascii() and value.isdigit():
        wait = max(wait, float(value))
    return min(wait, cap)
