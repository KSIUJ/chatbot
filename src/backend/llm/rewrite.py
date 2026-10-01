"""
Kondensacja pytania przed retrievalem: dopytanie typu "a jaki ma pokoj?" jest
przepisywane na samodzielne zapytanie na podstawie poprzednich pytan.
Dziala tylko z dostawca ollama; przy innych zapytanie wraca bez zmian.
"""

import logging
import os

from .ollama_client import chat
from .provider import OLLAMA, current_provider

logger = logging.getLogger(__name__)

DEFAULT_QUESTIONS = 5
MAX_LENGTH = 200
OFF_VALUES = {"0", "off", "false", "no", "nie"}

SYSTEM_PROMPT = (
    "Przepisujesz OSTATNIE PYTANIE na samodzielne zapytanie do wyszukiwarki. "
    "ZASADY:\n"
    "1. Rozwin zaimki (jego, jej, on, ona, to, tam) na podstawie HISTORII PYTAN.\n"
    "2. Nazwiska i nazwy podaj w mianowniku.\n"
    "3. Gdy w historii jest kilka osob lub tematow, wez ZAWSZE ten z NAJNOWSZEGO "
    "pytania (historia jest uporzadkowana od najstarszego do najnowszego).\n"
    "4. Jesli ostatnie pytanie dotyczy nowego tematu, zwroc je bez zmian - "
    "NIE dokrajaj nazwisk ani tematow z historii.\n"
    "5. Przepisane zapytanie MUSI zawierac nazwe lub nazwisko - nigdy nie zostawiaj "
    "samego zaimka ani czasownika bez podmiotu.\n"
    "6. Zwroc WYLACZNIE przepisane zapytanie, bez komentarza i cudzyslowow.\n\n"
    "PRZYKLADY:\n"
    "historia: 1. kim jest Jan Kowalski | ostatnie: a jaki ma numer telefonu?\n"
    "-> jaki numer telefonu ma Jan Kowalski\n"
    "historia: 1. kim jest Jan Kowalski, 2. jakie dyzury ma Anna Nowak | "
    "ostatnie: a gdzie jest jej pokoj?\n"
    "-> gdzie jest pokoj Anna Nowak\n"
    "historia: 1. kim jest Jan Kowalski | ostatnie: kiedy zaczyna sie sesja?\n"
    "-> kiedy zaczyna sie sesja"
)


def _previous_questions(history: list[dict[str, str]] | None, limit: int) -> list[str]:
    if not history or limit <= 0:
        return []
    questions = [m.get("content") or "" for m in history if m.get("role") == "user"]
    return [q for q in questions if q.strip()][-limit:]


def _is_enabled() -> bool:
    if os.getenv("CHAT_CONDENSE", "on").strip().lower() in OFF_VALUES:
        return False
    return current_provider() == OLLAMA


def condense(query: str, history: list[dict[str, str]] | None = None) -> str:
    """Zwraca samodzielne zapytanie do wyszukiwarki albo `query` bez zmian.

    Bez zmian, gdy: kondensacja wylaczona (CHAT_CONDENSE), dostawca inny niz
    ollama, brak poprzednich pytan, blad modelu lub nieprawidlowa odpowiedz.
    """
    if not _is_enabled():
        return query

    limit = int(os.getenv("CHAT_CONDENSE_QUESTIONS") or DEFAULT_QUESTIONS)
    questions = _previous_questions(history, limit)
    if not questions:
        return query

    user = "HISTORIA PYTAN (od najstarszego do najnowszego):\n"
    user += "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    user += f"\n\nNAJNOWSZE PYTANIE Z HISTORII: {questions[-1]}"
    user += f"\n\nOSTATNIE PYTANIE: {query}"

    try:
        rewritten = chat(system=SYSTEM_PROMPT, user=user, temperature=0.0, num_ctx=4096)
    except Exception as e:  # noqa: BLE001 - kondensacja jest opcjonalna
        logger.warning("Kondensacja zapytania nie powiodla sie, uzywam oryginalu: %s", e)
        return query

    lines = [line.strip() for line in (rewritten or "").splitlines() if line.strip()]
    if not lines:
        return query

    rewritten = lines[0].strip('"').strip()
    if not rewritten or len(rewritten) > MAX_LENGTH:
        return query
    return rewritten
