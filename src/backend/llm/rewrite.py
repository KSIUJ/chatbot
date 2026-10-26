"""
Kondensacja pytania przed retrievalem: dopytanie typu "a jaki ma pokoj?" jest
zamieniane na samodzielne zapytanie na podstawie poprzednich pytan i poczatku
ostatniej odpowiedzi (nazwisko bywa tylko w odpowiedzi: "opowiedz o tym prowadzacym").

Tryby (CHAT_CONDENSE):
- "on" (domyslnie): model wybranego dostawcy (ollama, claude, openrouter)
  przepisuje pytanie; przy bledzie, przekroczeniu czasu albo zlej odpowiedzi -
  regula ponizej. Cursor (agent, odpowiedz w dziesiatki sekund) od razu
  korzysta z reguly.
- "heuristic": tylko regula: gdy pytanie wyglada na dopytanie (krotkie,
  zaczyna sie od "a"/"i" albo ma zaimek, bez nazwy wlasnej), zapytaniem jest
  najnowsze poprzednie pytanie plus dopytanie.
- "off": zapytanie bez zmian.
"""

import logging
import os
import re
from collections.abc import Callable

from . import claude_client, ollama_client, openrouter_client
from .provider import current_provider, env_setting

logger = logging.getLogger(__name__)

DEFAULT_QUESTIONS = 5
MAX_LENGTH = 200
# tyle znakow ostatniej odpowiedzi dostaje model przepisujacy dopytanie
LAST_ANSWER_CHARS = 800
OFF_VALUES = {"0", "off", "false", "no", "nie"}
HEURISTIC_VALUES = {"heuristic", "rule", "regula"}
# limit czasu (s) przepisywania przez API (claude, openrouter)
DEFAULT_TIMEOUT = 8
# Claude Haiku 5.5 mysli adaptacyjnie, a mysli licza sie do max_tokens
CLAUDE_MAX_TOKENS = 1024

# dopytanie: najwyzej tyle slow
MAX_FOLLOWUP_WORDS = 8
FOLLOWUP_STARTS = {"a", "i", "oraz", "ale", "no"}
# zaimki odsylajace do poprzedniego pytania ("to" pomijamy - "co to jest X?")
ANAPHORA = {
    "on", "ona", "ono", "oni", "one", "jego", "jej", "go", "niego", "niej", "nim", "nią", "ją",
    "ich", "nich", "je", "im", "nimi", "ten", "ta", "te", "tego", "tej", "tym", "tę",
    "tam", "tamten", "tamta", "tamto", "tamtego", "tamtej",
}

SYSTEM_PROMPT = (
    "Przepisujesz OSTATNIE PYTANIE na samodzielne zapytanie do wyszukiwarki. "
    "ZASADY:\n"
    "1. Rozwin zaimki i odwolania (jego, jej, on, ona, to, tam, ten prowadzacy, ten przedmiot) na "
    "podstawie HISTORII PYTAN i OSTATNIEJ ODPOWIEDZI - nazwisko albo nazwa czesto jest tylko w odpowiedzi.\n"
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
    "-> kiedy zaczyna sie sesja\n"
    "historia: 1. kto prowadzi wyklad z analizy | ostatnia odpowiedz: Wyklad prowadzi dr Marcin Kulczycki. | "
    "ostatnie: opowiedz mi o tym prowadzacym\n"
    "-> kim jest Marcin Kulczycki"
)


def _last_answer(history: list[dict[str, str]] | None) -> str:
    """Poczatek ostatniej odpowiedzi asystenta - tam bywa nazwisko, do ktorego
    odwoluje sie dopytanie ("opowiedz o tym prowadzacym")."""
    for message in reversed(history or []):
        if message.get("role") == "assistant":
            text = " ".join((message.get("content") or "").split())
            return text[:LAST_ANSWER_CHARS]
    return ""


def _previous_questions(history: list[dict[str, str]] | None, limit: int) -> list[str]:
    if not history or limit <= 0:
        return []
    questions = [m.get("content") or "" for m in history if m.get("role") == "user"]
    return [q for q in questions if q.strip()][-limit:]


def _mode() -> str:
    """"on", "heuristic" albo "off" (CHAT_CONDENSE)."""
    value = os.getenv("CHAT_CONDENSE", "on").strip().lower()
    if value in OFF_VALUES:
        return "off"
    return "heuristic" if value in HEURISTIC_VALUES else "on"


def _timeout() -> int:
    return int(env_setting("CHAT_CONDENSE_TIMEOUT", str(DEFAULT_TIMEOUT)))


def _ollama(system: str, user: str) -> str:
    return ollama_client.chat(system=system, user=user, temperature=0.0, num_ctx=4096)


def _claude(system: str, user: str) -> str:
    # bez temperature - Claude Haiku 5.5 jej nie przyjmuje
    return claude_client.chat(system=system, user=user, timeout=_timeout(), max_tokens=CLAUDE_MAX_TOKENS)


def _openrouter(system: str, user: str) -> str:
    return openrouter_client.chat(system=system, user=user, temperature=0.0, timeout=_timeout())


# dostawcy, ktorych model przepisuje dopytania
_REWRITERS: dict[str, Callable[[str, str], str]] = {
    "ollama": _ollama,
    "claude": _claude,
    "openrouter": _openrouter,
}


def looks_like_followup(query: str) -> bool:
    """Czy pytanie wyglada na dopytanie: krotkie, bez nazwy wlasnej (wielka
    litera poza pierwszym slowem), zaczyna sie od "a"/"i" albo ma zaimek."""
    words = re.findall(r"\w+", query)
    if not words or len(words) > MAX_FOLLOWUP_WORDS:
        return False
    if any(word[0].isupper() for word in words[1:]):
        return False
    lowered = [word.lower() for word in words]
    return lowered[0] in FOLLOWUP_STARTS or any(word in ANAPHORA for word in lowered)


def heuristic_rewrite(query: str, questions: list[str]) -> str:
    """Najnowsze poprzednie pytanie + dopytanie; inne pytania bez zmian."""
    if not questions or not looks_like_followup(query):
        return query
    return f"{questions[-1].strip()} {query.strip()}"


def _llm_user_message(query: str, questions: list[str], last_answer: str = "") -> str:
    user = "HISTORIA PYTAN (od najstarszego do najnowszego):\n"
    user += "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    user += f"\n\nNAJNOWSZE PYTANIE Z HISTORII: {questions[-1]}"
    if last_answer:
        user += f"\n\nOSTATNIA ODPOWIEDZ (poczatek): {last_answer}"
    user += f"\n\nOSTATNIE PYTANIE: {query}"
    return user


def _clean(rewritten: str | None) -> str | None:
    """Pierwsza linia odpowiedzi modelu bez cudzyslowow; None, gdy pusta lub za dluga."""
    lines = [line.strip() for line in (rewritten or "").splitlines() if line.strip()]
    if not lines:
        return None
    cleaned = lines[0].strip('"').strip()
    return cleaned if cleaned and len(cleaned) <= MAX_LENGTH else None


def _llm_rewrite(provider: str, query: str, questions: list[str], last_answer: str = "") -> str | None:
    """Zapytanie przepisane przez model dostawcy; None przy bledzie lub zlej odpowiedzi."""
    try:
        reply = _REWRITERS[provider](SYSTEM_PROMPT, _llm_user_message(query, questions, last_answer))
    except Exception as e:  # noqa: BLE001 - kondensacja jest opcjonalna
        logger.warning("Kondensacja zapytania nie powiodla sie, uzywam reguly: %s", e)
        return None
    return _clean(reply)


def condense(query: str, history: list[dict[str, str]] | None = None) -> str:
    """Zwraca samodzielne zapytanie do wyszukiwarki albo `query` bez zmian.

    Bez zmian, gdy: kondensacja wylaczona, brak poprzednich pytan albo
    pytanie nie wyglada na dopytanie (a model nie przepisal go inaczej).
    """
    mode = _mode()
    if mode == "off":
        return query

    limit = int(os.getenv("CHAT_CONDENSE_QUESTIONS") or DEFAULT_QUESTIONS)
    questions = _previous_questions(history, limit)
    if not questions:
        return query

    provider = current_provider()
    if mode == "on" and provider in _REWRITERS:
        rewritten = _llm_rewrite(provider, query, questions, _last_answer(history))
        if rewritten:
            return rewritten
    return heuristic_rewrite(query, questions)
