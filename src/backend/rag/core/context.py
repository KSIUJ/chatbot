"""
Publiczny interfejs RAG dla warstwy LLM: retrieve_context(query) -> tekst
kontekstu do promptu, sciezki plikow-obrazow i zrodla odpowiedzi. Wywoluje go
llm/generate.py.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Iterable, Mapping
from typing import NamedTuple

from ..sources.base import RagSource
from .citations import Citation, collect_citations
from .index_store import LocationWatch
from .retrieval import Retriever, Section

_default_retriever: Retriever | None = None
_watch: LocationWatch | None = None
_index_name: str | None = None


def default_retriever() -> Retriever:
    """Wspolny retriever procesu (modele i indeksy laduja sie przy pierwszym uzyciu).

    Po przelaczeniu indeksu (python -m src.backend.rag.index build/sync)
    powstaje nowy retriever z tym samym encoderem - zrodla odbudowuja wtedy
    swoj stan, np. slownik nazwisk pracownikow."""
    global _default_retriever, _watch, _index_name
    if _watch is None:
        _watch = LocationWatch()
    name = _watch.current().name
    if _default_retriever is None:
        _default_retriever = Retriever()
    elif name != _index_name:
        _default_retriever = Retriever(encoder=_default_retriever.encoder)
    _index_name = name
    return _default_retriever


def loaded_retriever() -> Retriever | None:
    """Wspolny retriever, jesli juz powstal (diagnostyka nie laduje modeli)."""
    return _default_retriever


class RagContext(NamedTuple):
    prompt: str
    image_paths: list[str]
    # zrodla wszystkich trafien uzytych w kontekscie (tekst i obrazy)
    citations: list[Citation]


# Znaczniki promptu (llm/generate.py, llm/attachments.py), ktorych tresc fragmentu
# nie moze udawac - fragmenty pochodza ze stron i z USOS, gdzie pisac moze wiele osob.
_PROMPT_MARKERS = (
    "KONTEKST", "KONIEC KONTEKSTU", "PYTANIE", "ZAŁĄCZNIKI UŻYTKOWNIKA", "KONIEC ZAŁĄCZNIKÓW",
    "PLIKI DOŁĄCZONE DO ODPOWIEDZI", "PLIKI DOLACZONE DO ODPOWIEDZI",
)
# podpis fragmentu: "[usos: dr Jan Kowalski]"
_FRAGMENT_LABEL = re.compile(r"^\[[a-z_]+:\s")
_DECORATION = "#>*-+ \t"


def _folded(text: str) -> str:
    """Postac do porownan: NFKC, bez znakow niewidocznych, male litery, pojedyncze spacje."""
    normalized = unicodedata.normalize("NFKC", text)
    visible = "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")
    return " ".join(visible.casefold().split())


def _marker_names(headers: Iterable[str]) -> tuple[str, ...]:
    """Nazwy znacznikow: stale znaczniki promptu i naglowki sekcji bez opisu
    w nawiasie ("ŹRÓDŁA OFICJALNE (strony UJ ...):" -> "źródła oficjalne")."""
    names = {_folded(m) for m in _PROMPT_MARKERS}
    names.update(_folded(h.split(" (")[0].rstrip(":")) for h in headers if h)
    return tuple(name for name in names if name)


def _looks_like_marker(line: str, names: tuple[str, ...]) -> bool:
    folded = _folded(line).lstrip(_DECORATION)
    if _FRAGMENT_LABEL.match(folded):
        return True
    for name in names:
        rest = folded[len(name):] if folded.startswith(name) else None
        # sam znacznik, "ZNACZNIK:" albo "ZNACZNIK (opis)" - nie zwykle zdanie
        if rest is not None and (rest == "" or rest.startswith((":", " :", " (", "("))):
            return True
    return False


def neutralized(text: str, names: tuple[str, ...]) -> str:
    """Linie tresci udajace znaczniki promptu, naglowki sekcji albo podpisy
    fragmentow dostaja prefiks "> " - tekst ze strony czy USOS nie "zamknie"
    kontekstu i nie podszyje sie pod wiarygodniejsza sekcje (np. PRACOWNIK).
    splitlines() dzieli tez na U+2028 i podobne - model moze je czytac jak nowa linie."""
    return "\n".join(f"> {line}" if _looks_like_marker(line, names) else line for line in text.splitlines())


def _format_fragment(hit: dict, sources: Mapping[str, RagSource], names: tuple[str, ...]) -> str:
    name = hit.get("source", "?")
    source = sources.get(name)
    label = " ".join(str(source.label(hit) if source is not None else name).split())
    return f"[{name}: {label}]\n{neutralized(hit['value'], names)}"


def _section(section: Section, sources: Mapping[str, RagSource], names: tuple[str, ...]) -> str | None:
    fragments = [_format_fragment(h, sources, names) for h in section.hits if h.get("content_type") == "text"]
    if not fragments:
        return None
    return section.header + "\n\n" + "\n\n".join(fragments)


def render_sections(sections: list[Section], sources: Mapping[str, RagSource]) -> str:
    """Tekst kontekstu z sekcji: naglowek i fragmenty tekstowe; puste sekcje odpadaja."""
    from ..registry import POOLS  # tu, nie na gorze - registry importuje zrodla

    headers = [s.header for s in sections] + [p.header for p in POOLS]
    headers += [s.lookup_header for s in sources.values() if s.lookup_header]
    names = _marker_names(headers)
    return "\n\n".join(text for text in (_section(s, sources, names) for s in sections) if text)


def retrieve_context(query: str, retriever: Retriever | None = None) -> RagContext:
    """Kontekst dla zapytania: prompt, obrazy i zrodla.

    - prompt: fragmenty tekstowe oznaczone zrodlem, w sekcjach z
      Retriever.retrieve (dokladne wyszukiwania, potem pule z rejestru).
    - obrazy: wartosci trafien z content_type == "image" (skany, plany) -
      dolaczane do odpowiedzi jako pliki.
    - zrodla: strony, profile USOS i pliki z tych trafien, bez powtorzen.

    Brak trafien (np. pusty vectorstore) daje ("", [], []) zamiast wyjatku.
    """
    retriever = retriever or default_retriever()
    sections = retriever.retrieve(query)
    sources = retriever.sources

    prompt = render_sections(sections, sources)
    hits = [hit for section in sections for hit in section.hits]
    image_paths = [h["value"] for h in hits if h.get("content_type") == "image"]

    def cite(hit: dict) -> Citation | None:
        source = sources.get(hit.get("source", ""))
        return source.cite(hit) if source is not None else None

    return RagContext(prompt, image_paths, collect_citations(hits, cite))


def warm_up() -> float:
    """Laduje model embeddingow i indeksy wspolnego retrievera jednym probnym
    wyszukiwaniem - pierwsze pytanie uzytkownika nie czeka na wczytanie modelu
    (~20 s na CPU bez AVX). Zwraca czas w sekundach."""
    started = time.monotonic()
    default_retriever().retrieve("rozgrzewka")
    return time.monotonic() - started
