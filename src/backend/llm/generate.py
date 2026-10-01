"""Generowanie odpowiedzi: kondensacja pytania, kontekst z RAG i wywolanie LLM."""

import os
from collections.abc import Callable
from typing import TypedDict

from ..rag.context_builder import build_context
from . import claude_client, cursor_client, ollama_client, openrouter_client
from .provider import current_provider
from .rewrite import condense

SYSTEM_PROMPT = (
    "Jestes asystentem Wydzialu Matematyki i Informatyki UJ. ZASADY:\n"
    "1. Odpowiadaj ZAWSZE i wylacznie po polsku. Nigdy nie uzywaj chinskiego "
    "ani innego jezyka, nawet jesli kontekst jest w innym jezyku lub zawiera "
    "polamany tekst.\n"
    "2. Opieraj sie na sekcjach KONTEKST TEKSTOWY i PASUJACE PLIKI. Nie zmyslaj "
    "tresci, ktorej tam nie ma.\n"
    "3. Jesli jest sekcja PRACOWNIK, to WYLACZNIE ona zawiera dane o tej osobie "
    "(stanowisko, pokoj, telefon, dyzury, e-mail, zainteresowania). Gdy brakuje "
    "w niej danego pola - np. nie ma linii 'Pokoj:' - napisz wprost, ze tej "
    "informacji nie ma w USOS. NIGDY nie bierz numeru pokoju, telefonu ani "
    "e-maila z innych sekcji, z historii rozmowy ani z danych innej osoby.\n"
    "4. Sekcja ZRODLA OFICJALNE ma pierwszenstwo: przy pytaniach o pracownikow, "
    "dyzury, pokoje, regulaminy i terminy opieraj sie wylacznie na niej. "
    "MATERIALY STUDENCKIE traktuj jako pomocnicze i nie cytuj z nich danych "
    "kontaktowych ani zasad organizacyjnych.\n"
    "5. Jesli w PASUJACE PLIKI sa materialy pasujace do pytania, WSKAZ je "
    "uzytkownikowi po nazwie - nawet jesli nie znasz ich tresci. To czesto "
    "skany zadan/notatek, wiec sam plik jest odpowiedzia i zostanie dolaczony.\n"
    "6. Dopiero jesli naprawde nic nie pasuje, powiedz krotko, ze nie masz tego "
    "w materialach. Odpowiadaj rzeczowo i zwiezle.\n"
    "7. Nie zmyslaj, nie konfabuluj i nie wymyslaj odpowiedzi, gdy nie wiesz, o "
    "co chodzi. Szczegolnie nie wymyslaj nazwisk, stanowisk, numerow pokoi, "
    "godzin dyzurow ani innych danych kontaktowych.\n"
)

DEFAULT_HISTORY_MESSAGES = 4
DEFAULT_HISTORY_CHAR_LIMIT = 600

ChatFn = Callable[..., str]

_CHAT_FUNCTIONS: dict[str, ChatFn] = {
    "ollama": ollama_client.chat,
    "claude": claude_client.chat,
    "cursor": cursor_client.chat,
    "openrouter": openrouter_client.chat,
}


class Answer(TypedDict):
    answer: str
    files: list[str]


def _trim_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """Ostatnie CHAT_HISTORY_MESSAGES wiadomosci, kazda obcieta do CHAT_HISTORY_CHAR_LIMIT."""
    if not history:
        return []

    keep = int(os.getenv("CHAT_HISTORY_MESSAGES") or DEFAULT_HISTORY_MESSAGES)
    limit = int(os.getenv("CHAT_HISTORY_CHAR_LIMIT") or DEFAULT_HISTORY_CHAR_LIMIT)
    if keep <= 0:
        return []

    trimmed = []
    for message in history[-keep:]:
        content = message.get("content") or ""
        if len(content) > limit:
            content = content[:limit] + " [...]"
        trimmed.append({"role": message["role"], "content": content})
    return trimmed


def _format_files(files: list[str]) -> str:
    lines = []
    for path in files:
        name = os.path.basename(path)
        parent = os.path.basename(os.path.dirname(path))
        lines.append(f"- {name} (folder: {parent})")
    return "\n".join(lines)


def _resolve_chat_fn() -> ChatFn:
    """chat() dostawcy wybranego przez LLM_PROVIDER (patrz provider.py)."""
    return _CHAT_FUNCTIONS[current_provider()]


def answer(
    query: str,
    k_mordor: int = 5,
    k_other: int = 5,
    history: list[dict[str, str]] | None = None,
) -> Answer:
    """Odpowiada na pytanie z uzyciem RAG; zwraca tekst i sciezki dolaczanych plikow."""
    search_query = condense(query, history)
    context, files = build_context(search_query, k_mordor=k_mordor, k_other=k_other)

    parts = []
    if context.strip():
        parts.append(f"KONTEKST TEKSTOWY:\n{context}")
    if files:
        parts.append(
            "PASUJACE PLIKI (materialy/skany - tresci moze nie byc, ale mozesz "
            "je wskazac uzytkownikowi):\n" + _format_files(files)
        )
    if not parts:
        parts.append("(Brak pasujacego kontekstu i plikow w bazie.)")

    user_message = "\n\n".join(parts) + f"\n\nPYTANIE: {query}\n\nOdpowiedz po polsku."

    reply = _resolve_chat_fn()(
        system=SYSTEM_PROMPT, user=user_message, history=_trim_history(history)
    )
    return {"answer": reply, "files": files}
