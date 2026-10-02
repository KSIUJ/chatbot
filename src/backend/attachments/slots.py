"""Limit rownoczesnych wysylan plikow na osobe (w obrebie jednego procesu -
backend dziala na jednym workerze uvicorna)."""

from __future__ import annotations

import threading


class UploadSlots:
    """Licznik trwajacych wysylan per uzytkownik z gornym limitem."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._active: dict[str, int] = {}

    def try_acquire(self, user_id: str) -> bool:
        """Zajmuje miejsce; False = osoba ma juz limit trwajacych wysylan."""
        with self._lock:
            used = self._active.get(user_id, 0)
            if used >= self._limit:
                return False
            self._active[user_id] = used + 1
            return True

    def release(self, user_id: str) -> None:
        with self._lock:
            used = self._active.get(user_id, 0) - 1
            if used > 0:
                self._active[user_id] = used
            else:
                self._active.pop(user_id, None)

    def active(self, user_id: str) -> int:
        with self._lock:
            return self._active.get(user_id, 0)

    def reset(self) -> None:
        """Czysci liczniki (testy)."""
        with self._lock:
            self._active.clear()
