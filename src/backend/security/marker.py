"""Znacznik [[NARUSZENIE]], ktorym model (zasada 11 promptu) zaczyna odmowe
przy probie obejscia zasad. Uzytkownik go nie widzi i nie trafia do bazy;
jego obecnosc zaklada incydent dla zarzadu.

Liczy sie tylko znacznik na samym poczatku odpowiedzi (po bialych znakach) -
wzmianka dalej w tekscie zostaje bez zmian.
"""

from __future__ import annotations

import enum

VIOLATION_MARKER = "[[NARUSZENIE]]"


def strip_violation_marker(text: str) -> tuple[str, bool]:
    """(odpowiedz bez wiodacego znacznika i bialych znakow po nim, czy byl)."""
    head = text.lstrip()
    if not head.startswith(VIOLATION_MARKER):
        return text, False
    return head[len(VIOLATION_MARKER):].lstrip(), True


class _State(enum.Enum):
    # poczatek odpowiedzi - jeszcze nie wiadomo, czy to znacznik
    DECIDING = "deciding"
    # znacznik zdjety, pomijamy biale znaki tuz po nim
    SKIP_SPACE = "skip_space"
    # reszta odpowiedzi idzie bez zmian
    PASS = "pass"


class MarkerFilter:
    """Zdejmuje znacznik z odpowiedzi strumieniowanej. Znacznik moze byc
    rozciety miedzy kawalki, wiec poczatek odpowiedzi jest buforowany, dopoki
    nie wiadomo, czy jest prefiksem znacznika (najwyzej len(VIOLATION_MARKER)
    znakow poza bialymi). Uzycie: feed() dla kazdego kawalka, finish() na koncu;
    zwracany tekst idzie do klienta (pusty = nic do wyslania)."""

    def __init__(self) -> None:
        self._state = _State.DECIDING
        self._buffer = ""
        self.detected = False

    def feed(self, chunk: str) -> str:
        if self._state is _State.PASS:
            return chunk
        if self._state is _State.SKIP_SPACE:
            return self._skip_space(chunk)
        self._buffer += chunk
        head = self._buffer.lstrip()
        if not head or (len(head) < len(VIOLATION_MARKER) and VIOLATION_MARKER.startswith(head)):
            return ""
        buffered, self._buffer = self._buffer, ""
        if head.startswith(VIOLATION_MARKER):
            self.detected = True
            self._state = _State.SKIP_SPACE
            return self._skip_space(head[len(VIOLATION_MARKER):])
        self._state = _State.PASS
        return buffered

    def finish(self) -> str:
        """Koniec strumienia: niedokonczony prefiks znacznika to zwykly tekst."""
        buffered, self._buffer = self._buffer, ""
        self._state = _State.PASS
        return buffered

    def _skip_space(self, text: str) -> str:
        rest = text.lstrip()
        if rest:
            self._state = _State.PASS
        return rest
