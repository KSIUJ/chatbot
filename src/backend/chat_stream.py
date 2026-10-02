"""Odpowiedz strumieniowana jako Server-Sent Events (POST /chat/stream).

Zdarzenia: "delta" {"text"} - kolejne kawalki odpowiedzi, "done"
{"conversation_id", "message"} - zapisana odpowiedz, "error" {"code",
"message"} - porazka, nic nie zapisano.

Generator dziala po zakonczeniu zapytania HTTP, wiec otwiera wlasne sesje
bazy (session_factory). Przez cale generowanie i zapis trzyma blokade
rozmowy. Gdy klient zniknie (Stop, zamkniecie karty) w trakcie pisania
odpowiedzi, zapisuje pytanie i dotychczasowy tekst tak jak pelna odpowiedz,
a strumien od modelu zamyka.

Wiodacy znacznik [[NARUSZENIE]] (zasada 11 promptu) nigdy nie trafia do
klienta: poczatek odpowiedzi jest buforowany, dopoki nie wiadomo, czy to
znacznik (security/marker.py). Na koncu tury powstaje incydent, jesli
pytanie pasowalo do heurystyki albo model dal znacznik.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import Protocol

import anyio
from anyio import to_thread

from .chat import (
    ChatTurn,
    ConversationNotOwned,
    SessionFactory,
    load_history,
    record_turn_incident,
    save_answer,
    save_partial_answer,
)
from .history import conversation_lock
from .llm.generate import AnswerStream
from .llm.language import REFUSAL
from .rag.sources import Source
from .security.marker import MarkerFilter

logger = logging.getLogger(__name__)

LLM_FAILED = "llm_failed"
SAVE_FAILED = "save_failed"
CONVERSATION_NOT_FOUND = "conversation_not_found"

_ERROR_MESSAGES = {
    LLM_FAILED: "Nie udało się wygenerować odpowiedzi. Spróbuj ponownie.",
    SAVE_FAILED: "Nie udało się zapisać odpowiedzi. Spróbuj ponownie.",
    CONVERSATION_NOT_FOUND: "Nie znaleziono rozmowy.",
}

# co ile sekund sprawdzamy, czy blokada rozmowy jest juz wolna
LOCK_POLL_INTERVAL = 0.05

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

StreamAnswerFn = Callable[..., AnswerStream]


class DisconnectProbe(Protocol):
    """To, czego generator potrzebuje z Request (latwa atrapa w testach)."""

    async def is_disconnected(self) -> bool: ...


class _EmptyAnswer(RuntimeError):
    """Model nie zwrocil zadnego tekstu."""


@dataclass
class _Progress:
    chunks: Iterator[str] | None = None
    sources: list[Source] = field(default_factory=list)
    # tekst wyslany klientowi (bez znacznika [[NARUSZENIE]])
    parts: list[str] = field(default_factory=list)
    # zdejmuje wiodacy znacznik, nawet rozciety miedzy kawalki
    marker: MarkerFilter = field(default_factory=MarkerFilter)
    # odpowiedz zapisana albo porazka - wtedy niczego juz nie zapisujemy
    finished: bool = False
    # jakas odpowiedz (pelna albo czesciowa) jest w bazie
    saved: bool = False


def sse_event(event: str, data: Mapping[str, object]) -> str:
    """Jedno zdarzenie SSE; JSON w jednej linii (znaki nowej linii sa escapowane)."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error_event(code: str) -> str:
    return sse_event("error", {"code": code, "message": _ERROR_MESSAGES[code]})


def _start_answer(session_factory: SessionFactory, turn: ChatTurn, stream_answer: StreamAnswerFn) -> AnswerStream:
    """Historia z bazy + retrieval; model rusza dopiero przy pierwszym kawalku."""
    db = session_factory()
    try:
        history = load_history(db, turn)
    finally:
        db.close()
    return stream_answer(turn.question, history=history, language=turn.language)


async def chat_events(
    probe: DisconnectProbe,
    session_factory: SessionFactory,
    turn: ChatTurn,
    stream_answer: StreamAnswerFn,
) -> AsyncIterator[str]:
    """Zdarzenia SSE dla jednej tury czatu (patrz opis modulu)."""
    lock = conversation_lock(turn.conversation_id)
    progress = _Progress()
    await _acquire(lock)
    # od zdobycia blokady do "try" nie ma await - anulowanie nie zgubi blokady
    try:
        # klient mogl zniknac, czekajac na blokade - wtedy nie pytamy modelu
        if await probe.is_disconnected():
            return
        try:
            answer = await to_thread.run_sync(_start_answer, session_factory, turn, stream_answer)
            progress.chunks, progress.sources = answer.chunks, answer.sources
            while (chunk := await to_thread.run_sync(next, answer.chunks, None)) is not None:
                text = progress.marker.feed(chunk)
                if not text:
                    continue
                progress.parts.append(text)
                yield sse_event("delta", {"text": text})
                if await probe.is_disconnected():
                    return
            tail = progress.marker.finish()
            if progress.marker.detected and not "".join(progress.parts).strip() and not tail.strip():
                # sam znacznik - stala odmowa zamiast pustej odpowiedzi i bledu
                tail = REFUSAL[turn.language]
            if tail:
                progress.parts.append(tail)
                yield sse_event("delta", {"text": tail})
            full_text = "".join(progress.parts).strip()
            if not full_text:
                raise _EmptyAnswer("model returned no text")
        except ConversationNotOwned:
            progress.finished = True
            yield _error_event(CONVERSATION_NOT_FOUND)
            return
        except Exception:
            logger.exception("streamed answer failed (conversation %s)", turn.conversation_id)
            progress.finished = True
            yield _error_event(LLM_FAILED)
            return

        try:
            # oslona: zapis po anulowaniu bylby powtorzony jako czesciowy
            with anyio.CancelScope(shield=True):
                message = await to_thread.run_sync(save_answer, session_factory, turn, full_text, progress.sources)
                progress.finished = True
                progress.saved = True
        except Exception:
            logger.exception("saving streamed answer failed (conversation %s)", turn.conversation_id)
            progress.finished = True
            yield _error_event(SAVE_FAILED)
            return
        yield sse_event("done", {"conversation_id": turn.conversation_id, "message": message.model_dump(mode="json")})
    finally:
        try:
            with anyio.CancelScope(shield=True):
                await _finish(session_factory, turn, progress)
        finally:
            lock.release()


async def _acquire(lock: threading.Lock) -> None:
    """Czeka na blokade rozmowy bez zajmowania watku z puli (watki sa wspolne
    z endpointami synchronicznymi i z next() strumienia trzymajacego blokade).
    Anulowanie w trakcie czekania nie zostawia zdobytej blokady."""
    while not lock.acquire(blocking=False):
        await anyio.sleep(LOCK_POLL_INTERVAL)


async def _finish(session_factory: SessionFactory, turn: ChatTurn, progress: _Progress) -> None:
    """Zamyka strumien od modelu, zapisuje przerwana odpowiedz (jesli jest)
    i zglasza incydent (heurystyka i/lub znacznik od modelu)."""
    if progress.chunks is not None:
        close = getattr(progress.chunks, "close", None)
        if close is not None:
            try:
                await to_thread.run_sync(close)
            except Exception:
                logger.exception("closing LLM stream failed (conversation %s)", turn.conversation_id)
    if not progress.finished and progress.parts:
        try:
            saved = await to_thread.run_sync(
                partial(save_partial_answer, session_factory, turn, "".join(progress.parts), progress.sources)
            )
            progress.saved = saved is not None
        except Exception:
            logger.exception("saving partial answer failed (conversation %s)", turn.conversation_id)
    # record_turn_incident sam loguje swoje bledy
    await to_thread.run_sync(record_turn_incident, session_factory, turn, progress.marker.detected, progress.saved)
