"""
Wspolny podzial tekstu na chunki (zrodla z dlugimi tekstami: strony, mordor,
notatki KSI).

Tresc w Markdownie jest dzielona naglowkami (#, ##, ###) na sekcje; male
sasiednie sekcje sa laczone w jeden chunk (z naglowkami w tekscie), duze -
dzielone splitterem o parametrach CHUNK_SIZE/CHUNK_OVERLAP. Chunk pamieta
sciezke naglowkow, z ktorej pochodzi - zrodlo sklada z niej i z tytulu
linie kontekstu (context_line), dopisywana na poczatku tekstu do
wyszukiwania i tekstu dla modelu (with_context).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

# Zmiana parametrow zmienia chunki (i ich id) - wymaga ponownego ingestu z --purge.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
# naglowki glebsze niz ### zostaja zwyklym tekstem
MAX_HEADING_LEVEL = 3
# separator czesci linii kontekstu: "Tytul strony › Sekcja › Podsekcja"
CONTEXT_SEPARATOR = " › "
MAX_CONTEXT_PART = 120

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")
_EMPHASIS = re.compile(r"[*_`]+")


def make_splitter() -> RecursiveCharacterTextSplitter:
    """Splitter o parametrach CHUNK_SIZE/CHUNK_OVERLAP."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Section:
    # naglowki od ogolu do szczegolu (pusto = tekst przed pierwszym naglowkiem)
    headings: tuple[Heading, ...]
    text: str


@dataclass(frozen=True)
class Chunk:
    # tekst chunka bez linii kontekstu
    text: str
    # sciezka naglowkow wspolna dla calego chunka
    section: tuple[str, ...]


def _clean_heading(text: str) -> str:
    return " ".join(_EMPHASIS.sub("", text).split()).rstrip(":")


def split_sections(markdown: str) -> list[Section]:
    """Sekcje tekstu wedlug naglowkow do MAX_HEADING_LEVEL (poza blokami kodu)."""
    sections: list[Section] = []
    path: list[Heading] = []
    lines: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text or path:
            sections.append(Section(tuple(path), text))
        lines.clear()

    for line in markdown.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match and len(match.group(1)) <= MAX_HEADING_LEVEL and _clean_heading(match.group(2)):
            flush()
            level = len(match.group(1))
            path = [h for h in path if h.level < level] + [Heading(level, _clean_heading(match.group(2)))]
        else:
            lines.append(line)
    flush()
    return sections


def _common_prefix(paths: Iterable[tuple[Heading, ...]]) -> tuple[Heading, ...]:
    paths = list(paths)
    prefix = paths[0]
    for path in paths[1:]:
        size = 0
        while size < min(len(prefix), len(path)) and prefix[size] == path[size]:
            size += 1
        prefix = prefix[:size]
    return prefix


def _render(group: Sequence[Section]) -> str:
    """Tekst grupy sekcji: naglowki ponizej wspolnej sciezki wpisane w tekst."""
    base = len(_common_prefix(s.headings for s in group))
    parts: list[str] = []
    previous: tuple[Heading, ...] = ()
    for section in group:
        shared = len(_common_prefix([previous, section.headings])) if previous else 0
        for heading in section.headings[max(base, shared):]:
            parts.append(f"{'#' * heading.level} {heading.text}")
        if section.text:
            parts.append(section.text)
        previous = section.headings
    return "\n\n".join(parts)


def _groups(sections: list[Section]) -> list[list[Section]]:
    """Sasiednie sekcje laczone, dopoki razem mieszcza sie w CHUNK_SIZE."""
    groups: list[list[Section]] = []
    current: list[Section] = []
    for section in sections:
        if current and len(_render([*current, section])) <= CHUNK_SIZE:
            current.append(section)
            continue
        if current:
            groups.append(current)
        current = [section]
    if current:
        groups.append(current)
    return groups


def chunk_markdown(markdown: str, splitter: RecursiveCharacterTextSplitter | None = None) -> list[Chunk]:
    """Chunki tekstu w Markdownie: sekcje wedlug naglowkow, male laczone,
    duze dzielone splitterem. Tekst bez naglowkow dzieli sie jak dawniej."""
    splitter = splitter or make_splitter()
    chunks: list[Chunk] = []
    # sekcja bez tekstu (naglowek tuz przed podsekcja) - jej naglowek jest i tak
    # w sciezce kolejnych sekcji
    sections = [s for s in split_sections(markdown) if s.text]
    for group in _groups(sections):
        section = tuple(h.text for h in _common_prefix(s.headings for s in group))
        body = _render(group)
        pieces = [body] if len(body) <= CHUNK_SIZE else splitter.split_text(body)
        chunks.extend(Chunk(piece, section) for piece in pieces if piece.strip())
    return chunks


def _short(part: str) -> str:
    part = " ".join(part.split())
    return part if len(part) <= MAX_CONTEXT_PART else part[: MAX_CONTEXT_PART - 1].rstrip() + "…"


def context_line(*parts: str) -> str:
    """Linia kontekstu chunka, np. "O nas › Biblioteka › Godziny otwarcia".
    Puste czesci odpadaja, powtorzenia (bez wielkosci liter) tez - tytul
    bywa tez pierwszym naglowkiem albo ostatnim elementem okruszkow."""
    kept: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = _short(part or "")
        key = part.casefold()
        if part and key not in seen:
            seen.add(key)
            kept.append(part)
    return CONTEXT_SEPARATOR.join(kept)


def with_context(context: str, text: str) -> str:
    """Tekst chunka poprzedzony linia kontekstu (pierwsza linia trafia tez do
    pola tytulu w indeksie BM25 - lexical.py)."""
    return f"{context}\n{text}" if context else text
