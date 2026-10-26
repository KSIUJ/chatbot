"""Odpowiedz strumieniowana jako Server-Sent Events (POST /chat/stream).

Zdarzenia: "delta" {"text"} - kolejne kawalki odpowiedzi, "done"
{"conversation_id", "message"} - zapisana odpowiedz, "error" {"code",
"message"} - porazka, nic nie zapisano.

Odpowiedz powstaje we wlasnym watku (_Producer), niezaleznie od polaczenia:
generator SSE tylko przekazuje klientowi to, co watek juz napisal. Dzieki
temu odswiezenie strony albo zamkniecie karty nie przerywa odpowiedzi - model
pisze dalej, pelna odpowiedz trafia do bazy, a frontend po powrocie pokazuje
ja z GET /chat/pending (chat_runs.py). Przerywa tylko przycisk Stop (POST
/chat/stop): watek konczy po biezacym kawalku i zapisuje pytanie i dotychczasowy
tekst tak jak pelna odpowiedz. Watek trzyma blokade rozmowy do konca zapisu
i otwiera wlasne sesje bazy (session_factory).

Dzienny limit pytan jest zuzywany przed strumieniem (main.py). Pytanie wraca
do puli (`refund`) tylko po bledzie po stronie serwera: blad modelu, pusta
odpowiedz, nieudany zapis. Stop i rozlaczenie nigdy nie zwracaja pytania -
inaczej petla "wyslij i przerwij" dawalaby nielimitowane wywolania modelu.

Wiodacy znacznik [[NARUSZENIE]] (zasada 18 promptu) nigdy nie trafia do
klienta: poczatek odpowiedzi jest buforowany, dopoki nie wiadomo, czy to
znacznik (security/marker.py). Incydent (heurystyka albo znacznik) jest zapisywany
przed "done" (po bledzie - na koncu tury), wiec blokada po ostatnim
ostrzezeniu (security/blocks.py) jest juz widoczna w /usage.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Protocol

import anyio
from anyio import to_thread

from . import chat_runs
from .chat import (
    ChatTurn,
    ConversationNotOwned,
    SessionFactory,
    load_history,
    model_kwargs,
    record_turn_incident,
    save_answer,
    save_partial_answer,
)
from .history import conversation_lock
from .llm.generate import AnswerStream
from .llm.language import REFUSAL
from .llm.tools import ToolBox
from .rag.core.citations import Citation
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
# najdluzsze czekanie na kolejne zdarzenie z watku, zanim sprawdzimy polaczenie
EVENT_POLL_INTERVAL = 0.25

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

StreamAnswerFn = Callable[..., AnswerStream]
# zwrot zuzytego pytania, gdy nic nie zostalo zapisane
RefundFn = Callable[[], None]


class DisconnectProbe(Protocol):
    """To, czego generator potrzebuje z Request (latwa atrapa w testach)."""

    async def is_disconnected(self) -> bool: ...


class _EmptyAnswer(RuntimeError):
    """Model nie zwrocil zadnego tekstu."""


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
    return stream_answer(turn.question, history=history, **model_kwargs(turn))


# koniec zdarzen z watku
_END = object()


@dataclass
class _Producer:
    """Jedna tura w watku: model -> zdarzenia SSE w kolejce -> zapis. Zwalnia
    blokade rozmowy i wpis w chat_runs na samym koncu."""

    session_factory: SessionFactory
    turn: ChatTurn
    stream_answer: StreamAnswerFn
    refund: RefundFn | None
    lock: threading.Lock
    active: chat_runs.ActiveTurn
    events: queue.Queue = field(default_factory=queue.Queue)
    chunks: Iterator[str] | None = None
    sources: list[Citation] = field(default_factory=list)
    tools: ToolBox | None = None
    parts: list[str] = field(default_factory=list)
    marker: MarkerFilter = field(default_factory=MarkerFilter)
    saved: bool = False
    server_failed: bool = False
    incident_recorded: bool = False

    def _delta(self, text: str) -> None:
        self.parts.append(text)
        self.active.append(text)
        self.events.put(sse_event("delta", {"text": text}))

    def run(self) -> None:
        try:
            self._generate()
        except Exception:  # _generate sam obsluguje bledy - to tylko ostatnia oslona
            logger.exception("chat turn failed (conversation %s)", self.turn.conversation_id)
        finally:
            try:
                self._finish()
            finally:
                chat_runs.finish(self.active)
                self.lock.release()
                self.events.put(_END)

    def _generate(self) -> None:
        turn = self.turn
        try:
            answer = _start_answer(self.session_factory, turn, self.stream_answer)
            self.chunks, self.sources, self.tools = answer.chunks, answer.sources, answer.tools
            for chunk in self.chunks:
                text = self.marker.feed(chunk)
                if text:
                    self._delta(text)
                if self.active.stop.is_set():
                    # Stop: zapis tego, co jest (_finish)
                    return
            tail = self.marker.finish()
            if self.marker.detected and not "".join(self.parts).strip() and not tail.strip():
                # sam znacznik - stala odmowa zamiast pustej odpowiedzi i bledu
                tail = REFUSAL[turn.language]
            if tail:
                self._delta(tail)
            full_text = "".join(self.parts).strip()
            if not full_text:
                raise _EmptyAnswer("model returned no text")
        except ConversationNotOwned:
            self.parts.clear()
            self.events.put(_error_event(CONVERSATION_NOT_FOUND))
            return
        except Exception:
            logger.exception("streamed answer failed (conversation %s)", turn.conversation_id)
            self.parts.clear()
            self.server_failed = True
            self.events.put(_error_event(LLM_FAILED))
            return

        try:
            message = save_answer(self.session_factory, turn, full_text, *self._saved_sources())
            self.saved = True
        except Exception:
            logger.exception("saving streamed answer failed (conversation %s)", turn.conversation_id)
            self.server_failed = True
            self.events.put(_error_event(SAVE_FAILED))
            return
        finally:
            # zapisane albo porazka - _finish nie zapisuje drugi raz
            self.parts.clear()
        # incydent i ewentualna blokada przed "done": klient zaraz potem pyta o /usage
        record_turn_incident(self.session_factory, turn, self.marker.detected, True)
        self.incident_recorded = True
        self.events.put(sse_event("done", {"conversation_id": turn.conversation_id, "message": message.model_dump(mode="json")}))

    def _saved_sources(self) -> tuple[list[Citation], bool]:
        """Zrodla do zapisu i czy odpowiedz opiera sie na danych osoby (model
        uzyl narzedzi z USOS) - wtedy dochodzi zrodlo "Twoje dane z USOS"."""
        if self.tools is None or not self.tools.used:
            return self.sources, False
        return [*self.sources, *self.tools.citations], True

    def _finish(self) -> None:
        """Zamyka strumien od modelu, zapisuje przerwana odpowiedz (Stop),
        zwraca pytanie do limitu po bledzie serwera i zglasza incydent
        (heurystyka i/lub znacznik od modelu)."""
        turn = self.turn
        close = getattr(self.chunks, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                logger.exception("closing LLM stream failed (conversation %s)", turn.conversation_id)
        if self.parts:
            try:
                self.saved = save_partial_answer(
                    self.session_factory, turn, "".join(self.parts), *self._saved_sources()
                ) is not None
            except Exception:
                logger.exception("saving partial answer failed (conversation %s)", turn.conversation_id)
        if self.server_failed and not self.saved and self.refund is not None:
            try:
                self.refund()
            except Exception:
                logger.exception("refunding question failed (conversation %s)", turn.conversation_id)
        # record_turn_incident sam loguje swoje bledy
        if not self.incident_recorded:
            record_turn_incident(self.session_factory, turn, self.marker.detected, self.saved)


async def chat_events(
    probe: DisconnectProbe,
    session_factory: SessionFactory,
    turn: ChatTurn,
    stream_answer: StreamAnswerFn,
    refund: RefundFn | None = None,
) -> AsyncIterator[str]:
    """Zdarzenia SSE dla jednej tury czatu (patrz opis modulu). `refund`
    jest wolany raz, gdy tura konczy sie bledem serwera bez zapisanej
    odpowiedzi - nigdy po Stop ani rozlaczeniu klienta."""
    lock = conversation_lock(turn.conversation_id)
    await _acquire(lock)
    # od zdobycia blokady do przekazania jej watkowi nie ma await - anulowanie
    # jej nie zgubi
    try:
        active = chat_runs.start(turn.user_id, turn.conversation_id, turn.question)
        producer = _Producer(session_factory, turn, stream_answer, refund, lock, active)
        thread = threading.Thread(target=producer.run, name=f"chat-{turn.conversation_id}", daemon=True)
    except BaseException:
        lock.release()
        raise
    # klient mogl zniknac, czekajac na blokade - wtedy nie pytamy modelu
    try:
        gone = await probe.is_disconnected()
    except BaseException:
        chat_runs.finish(active)
        lock.release()
        raise
    if gone:
        chat_runs.finish(active)
        lock.release()
        return
    thread.start()

    while True:
        try:
            event = await to_thread.run_sync(producer.events.get, True, EVENT_POLL_INTERVAL)
        except queue.Empty:
            event = None
        if event is _END:
            return
        if event is not None:
            yield event
        # klient zniknal (odswiezenie, zamkniecie karty): watek pisze dalej i zapisze odpowiedz
        if await probe.is_disconnected():
            return


async def _acquire(lock: threading.Lock) -> None:
    """Czeka na blokade rozmowy bez zajmowania watku z puli (watki sa wspolne
    z endpointami synchronicznymi i z next() strumienia trzymajacego blokade).
    Anulowanie w trakcie czekania nie zostawia zdobytej blokady."""
    while not lock.acquire(blocking=False):
        await anyio.sleep(LOCK_POLL_INTERVAL)
