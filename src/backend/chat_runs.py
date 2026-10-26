"""Odpowiedzi w toku (w pamieci procesu - backend ma jeden worker).

Odpowiedz strumieniowana (chat_stream.py) jest tu zapisana od zdobycia
blokady rozmowy do zapisu w bazie. Dzieki temu:
- odswiezenie strony albo zamkniecie karty nie przerywa odpowiedzi - model
  pisze dalej, a frontend po powrocie pokazuje pytanie i dotychczasowy tekst
  (GET /chat/pending) i czeka na zapis,
- przycisk Stop (POST /chat/stop) to wyrazna prosba o przerwanie, odrozniona
  od zerwanego polaczenia.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from .models import utcnow


@dataclass
class ActiveTurn:
    user_id: str
    conversation_id: str
    question: str
    started_at: datetime = field(default_factory=utcnow)
    # tekst odpowiedzi wyslany dotad (bez znacznika [[NARUSZENIE]])
    text: str = ""
    stop: threading.Event = field(default_factory=threading.Event)

    def append(self, text: str) -> None:
        with _lock:
            self.text += text


_lock = threading.Lock()
_active: dict[str, ActiveTurn] = {}


def start(user_id: str, conversation_id: str, question: str) -> ActiveTurn:
    """Odpowiedz w toku dla rozmowy (wolane pod blokada rozmowy - jedna naraz)."""
    turn = ActiveTurn(user_id, conversation_id, question)
    with _lock:
        _active[conversation_id] = turn
    return turn


def finish(turn: ActiveTurn) -> None:
    with _lock:
        if _active.get(turn.conversation_id) is turn:
            del _active[turn.conversation_id]


def for_user(user_id: str) -> list[ActiveTurn]:
    """Odpowiedzi w toku osoby, od najnowszej."""
    with _lock:
        turns = [t for t in _active.values() if t.user_id == user_id]
    return sorted(turns, key=lambda t: t.started_at, reverse=True)


def request_stop(user_id: str, conversation_id: str) -> bool:
    """Prosba o przerwanie odpowiedzi; False = nie ma takiej odpowiedzi w toku
    (juz zapisana) albo rozmowa nalezy do kogos innego."""
    with _lock:
        turn = _active.get(conversation_id)
    if turn is None or turn.user_id != user_id:
        return False
    turn.stop.set()
    return True


def snapshot(turn: ActiveTurn) -> tuple[str, str, datetime, str]:
    with _lock:
        return turn.conversation_id, turn.question, turn.started_at, turn.text
