"""
Przedmiot, rok akademicki i rodzaj materialu odgadywane ze sciezki pliku
w Mordorze (np. "Informatyka/Rok 2/Bazy danych/Egzaminy/2023-2024/egz.pdf"
-> "Bazy danych", "2023/24", "egzamin").

- rok: "2023-2024", "2023/24", "23_24" -> "2023/24"; sam rok "2023" ->
  "2023/24"; najpierw z nazwy pliku, potem z katalogow od najglebszego
- rodzaj: slowa kluczowe w katalogach i nazwie pliku (KINDS), kilka naraz
  -> "kolokwium, rozwiązania"
- przedmiot: pierwszy od gory katalog, ktory nie jest ogolny (kierunek, rok,
  semestr, rodzaj materialu, rok akademicki - GENERIC_WORDS)
"""

from __future__ import annotations

import posixpath
import re
from typing import NamedTuple

from ...core.lexical import fold

# lata akademickie z sensownego zakresu (materialy studenckie)
MIN_YEAR, MAX_YEAR = 1995, 2039

_YEAR_RANGE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*[-_/.]\s*((?:19|20)?\d{2})(?!\d)")
_SHORT_RANGE = re.compile(r"(?<!\d)(\d{2})\s*[-_/]\s*(\d{2})(?!\d)")
_SINGLE_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_TOKEN = re.compile(r"[a-z]+|\d+")

# rodzaj materialu: (nazwa, cale slowa, poczatki slow) - slowa bez polskich znakow
KINDS: tuple[tuple[str, frozenset[str], tuple[str, ...]], ...] = (
    ("egzamin", frozenset({"egz", "exam", "exams"}), ("egzamin", "poprawk")),
    ("kolokwium", frozenset({"kol", "kolos", "kolosy", "midterm"}), ("kolokw", "sprawdzian")),
    ("rozwiązania", frozenset({"rozw", "sol", "odp"}), ("rozwiaz", "solution", "odpowiedz")),
    ("zadania", frozenset({"zad", "lista", "listy", "zestaw", "zestawy"}), ("zadani", "zadan", "exercise", "homework")),
    ("notatki", frozenset({"notes"}), ("notatk", "skrypt", "konspekt")),
    ("wykład", frozenset({"wyk", "lecture", "lectures", "slajdy", "slides"}), ("wyklad", "prezentac")),
    ("ćwiczenia", frozenset({"cw", "cwicz"}), ("cwiczen", "tutorial")),
    ("laboratorium", frozenset({"lab", "labs", "laby"}), ("laborator", "pracowni")),
    ("projekt", frozenset(), ("projekt", "project")),
    ("ściąga", frozenset(), ("sciag", "cheatsheet")),
)

# katalogi, ktore nie sa przedmiotem: kierunki, lata, semestry, porzadkowe
GENERIC_WORDS = frozenset(
    {
        "rok", "roku", "semestr", "sem", "stopien", "stopnia", "studia", "letni", "zimowy", "zima", "lato",
        "i", "ii", "iii", "iv", "v", "pierwszy", "drugi", "trzeci", "czwarty", "piaty",
        "informatyka", "matematyka", "analityczna", "komputerowa", "sztuczna", "inteligencja",
        "licencjat", "licencjackie", "magisterka", "magisterskie", "inzynierskie", "mgr", "lic",
        "materialy", "pliki", "inne", "rozne", "stare", "nowe", "archiwum", "mordor", "file", "files",
        "przedmioty", "obowiazkowe", "obieralne", "fakultety", "wybieralne", "kursy",
        "grupa", "gr", "termin", "zerowy", "poprawkowy", "skany", "skan", "zdjecia", "foto", "kopia",
    }
)


class PathInfo(NamedTuple):
    course: str
    academic_year: str
    material_kind: str


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(fold(text).lower())


def _year_range(first: int, second: int) -> str:
    return f"{first}/{second % 100:02d}" if (first + 1) % 100 == second % 100 else ""


def academic_year(text: str) -> str:
    """Rok akademicki zapisany w tekscie ("2023-2024", "23_24", "2023") albo ""."""
    for match in _YEAR_RANGE.finditer(text):
        first = int(match.group(1))
        if MIN_YEAR <= first <= MAX_YEAR and (year := _year_range(first, int(match.group(2)))):
            return year
    for match in _SHORT_RANGE.finditer(text):
        first = 2000 + int(match.group(1))
        if MIN_YEAR <= first <= MAX_YEAR and (year := _year_range(first, int(match.group(2)))):
            return year
    for match in _SINGLE_YEAR.finditer(text):
        first = int(match.group(1))
        if MIN_YEAR <= first <= MAX_YEAR:
            return _year_range(first, first + 1)
    return ""


def _kind_of(token: str) -> str | None:
    for name, words, prefixes in KINDS:
        if token in words or token.startswith(prefixes):
            return name
    return None


def material_kinds(texts: list[str]) -> str:
    """Rodzaje materialu z katalogow i nazwy pliku, w kolejnosci KINDS."""
    found = {kind for text in texts for token in _tokens(text) if (kind := _kind_of(token))}
    return ", ".join(name for name, _, _ in KINDS if name in found)


def _is_generic(segment: str) -> bool:
    tokens = _tokens(segment)
    return all(t.isdigit() or t in GENERIC_WORDS or _kind_of(t) for t in tokens)


def course_name(directories: list[str]) -> str:
    """Pierwszy od gory katalog, ktory nie jest ogolny; "" gdy brak."""
    for segment in directories:
        if not _is_generic(segment):
            return " ".join(segment.replace("_", " ").split())
    return ""


def parse_path(path: str) -> PathInfo:
    """Przedmiot, rok akademicki i rodzaj materialu ze sciezki pliku (z "/")."""
    *directories, filename = path.split("/")
    stem = posixpath.splitext(filename)[0]
    year = next((y for y in (academic_year(t) for t in [stem, *reversed(directories)]) if y), "")
    return PathInfo(course_name(directories), year, material_kinds([*directories, stem]))
