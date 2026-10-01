"""Generowanie odpowiedzi: kondensacja pytania, kontekst z RAG i wywolanie LLM."""

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import NamedTuple, TypedDict

from ..rag.context_builder import retrieve_context
from ..rag.sources import Source
from . import claude_client, cursor_client, ollama_client, openrouter_client
from .language import DEFAULT_LANGUAGE, Language
from .provider import current_provider
from .rewrite import condense

# Jezyk odpowiedzi w regule 1 promptu systemowego
_LANGUAGE_NAMES: dict[Language, str] = {
    "pl": "po polsku",
    "en": "po angielsku (English)",
    "fr": "po francusku (français)",
}

# Ostatnia linia wiadomosci uzytkownika - w jezyku odpowiedzi
_ANSWER_IN: dict[Language, str] = {
    "pl": "Odpowiedz po polsku.",
    "en": "Answer in English.",
    "fr": "Réponds en français.",
}

_SYSTEM_PROMPT_TEMPLATE = (
    "Jestes asystentem Wydzialu Matematyki i Informatyki UJ. ZASADY:\n"
    "1. Odpowiadaj ZAWSZE i wylacznie {language}, takze gdy pytanie albo "
    "kontekst (dokumenty sa w jezyku polskim) sa w innym jezyku. Nigdy nie uzywaj "
    "chinskiego ani innego jezyka, nawet jesli kontekst zawiera polamany tekst.\n"
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
StreamFn = Callable[..., Iterator[str]]


class ProviderFns(NamedTuple):
    chat: ChatFn
    stream: StreamFn


# Jedno mapowanie dostawcy na funkcje - /chat i /chat/stream uzywaja tego samego
_PROVIDERS: dict[str, ProviderFns] = {
    "ollama": ProviderFns(ollama_client.chat, ollama_client.stream_chat),
    "claude": ProviderFns(claude_client.chat, claude_client.stream_chat),
    "cursor": ProviderFns(cursor_client.chat, cursor_client.stream_chat),
    "openrouter": ProviderFns(openrouter_client.chat, openrouter_client.stream_chat),
}


class Answer(TypedDict):
    answer: str
    files: list[str]
    sources: list[Source]


@dataclass(frozen=True)
class AnswerStream:
    """Odpowiedz strumieniowana: kawalki tekstu (leniwie - model rusza przy
    pierwszym next()) oraz pliki i zrodla znane juz po retrievalu."""
    chunks: Iterator[str]
    files: list[str]
    sources: list[Source]


class _Prompt(NamedTuple):
    system: str
    user: str
    history: list[dict[str, str]]
    files: list[str]
    sources: list[Source]


def system_prompt(language: Language = DEFAULT_LANGUAGE) -> str:
    """Prompt systemowy z regula jezyka odpowiedzi."""
    return _SYSTEM_PROMPT_TEMPLATE.format(language=_LANGUAGE_NAMES[language])


SYSTEM_PROMPT = system_prompt()


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
    return _PROVIDERS[current_provider()].chat


def _resolve_stream_fn() -> StreamFn:
    """stream_chat() dostawcy wybranego przez LLM_PROVIDER."""
    return _PROVIDERS[current_provider()].stream


def _build_prompt(
    query: str,
    k_mordor: int,
    k_other: int,
    history: list[dict[str, str]] | None,
    language: Language,
) -> _Prompt:
    """Kondensacja pytania, retrieval i prompt - wspolne dla answer() i stream_answer()."""
    search_query = condense(query, history)
    context, files, sources = retrieve_context(search_query, k_mordor=k_mordor, k_other=k_other)

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

    user_message = "\n\n".join(parts) + f"\n\nPYTANIE: {query}\n\n{_ANSWER_IN[language]}"
    return _Prompt(system_prompt(language), user_message, _trim_history(history), files, sources)


def answer(
    query: str,
    k_mordor: int = 5,
    k_other: int = 5,
    history: list[dict[str, str]] | None = None,
    language: Language = DEFAULT_LANGUAGE,
) -> Answer:
    """Odpowiada na pytanie z uzyciem RAG; zwraca tekst, sciezki dolaczanych
    plikow i zrodla."""
    prompt = _build_prompt(query, k_mordor, k_other, history, language)
    reply = _resolve_chat_fn()(system=prompt.system, user=prompt.user, history=prompt.history)
    return {"answer": reply, "files": prompt.files, "sources": prompt.sources}


def stream_answer(
    query: str,
    k_mordor: int = 5,
    k_other: int = 5,
    history: list[dict[str, str]] | None = None,
    language: Language = DEFAULT_LANGUAGE,
) -> AnswerStream:
    """Jak answer(), ale tekst przychodzi kawalkami. Retrieval dzieje sie od
    razu, zapytanie do modelu - przy pierwszym kawalku."""
    prompt = _build_prompt(query, k_mordor, k_other, history, language)
    chunks = _resolve_stream_fn()(system=prompt.system, user=prompt.user, history=prompt.history)
    return AnswerStream(chunks=chunks, files=prompt.files, sources=prompt.sources)
