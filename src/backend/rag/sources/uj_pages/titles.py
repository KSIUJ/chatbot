"""
Tytul i okruszki strony wyprowadzone z adresu - dla starego wyjscia crawlera
(legacy.py), ktore nie ma tytulow ani menu.

- zwykla strona: segmenty sciezki jako okruszki, ostatni = tytul
  (/o-nas/biblioteka -> ["O nas", "Biblioteka"]); polskie znaki odtwarzane
  ze slownika slow z tresci stron (Vocabulary: "wydzialu" -> "Wydziału")
- plik Liferay (/documents/<id>/<id>/<plik>[.pdf]/<uuid>): nazwa pliku bez
  rozszerzenia
- aktualnosc Liferay (/<dzial>/-/journal_content/.../<id>): pierwsza linia
  albo zdanie tresci, okruszki [dzial, tytul]
- strona glowna witryny: pierwsza krotka linia tresci albo host
- Wikipedia: tytul artykulu
"""

from __future__ import annotations

import posixpath
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import NamedTuple
from urllib.parse import unquote_plus, urlsplit

from ...core.lexical import fold

MAX_TITLE = 100
# slowo z adresu zostaje bez polskich znakow, gdy tak tez wystepuje w tekstach
# (co najmniej taka czesc wystapien najczestszej pisowni)
PLAIN_SHARE = 0.2
LANG_SEGMENTS = {"pl", "en", "en-gb", "en-us", "pl-pl", "de"}
FILE_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".odt", ".xlsx", ".xls", ".pptx", ".ppt", ".rtf"}
NEWS_MARKER = "journal_content"
WIKIPEDIA_HOST = "pl.wikipedia.org"
# witryny, ktorych host dopisujemy na poczatku okruszkow (kola naukowe, inne
# strony) - nazwa hosta bywa jedynym sladem nazwy kola (knmf, nkr.si)
HOST_PREFIXED = ("student_group", "other")

_WORD = re.compile(r"\w+", re.UNICODE)
_SLUG_SPLIT = re.compile(r"[-_+\s]+")
_TRAILING_NUMBER = re.compile(r"(?<=[a-z])\d+$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


class PageTitle(NamedTuple):
    title: str
    breadcrumbs: list[str]


class Vocabulary:
    """Pisownia slowa z tresci stron dla jego formy bez polskich znakow - do
    odtwarzania slow z adresow. Wielka litera tylko, gdy slowo pisane jest
    tak w srodku zdan (nazwy wlasne) albo ma wielkie litery w srodku (USOS)."""

    def __init__(self, texts: Iterable[str] = ()) -> None:
        self._exact: dict[str, Counter[str]] = defaultdict(Counter)
        # w srodku zdania: ile razy wielka litera, ile mala
        self._capitalized: Counter[str] = Counter()
        self._lowercase: Counter[str] = Counter()
        for text in texts:
            for line in text.splitlines():
                self._add_line(line)

    def _add_line(self, line: str) -> None:
        at_start, previous_end = True, 0
        for match in _WORD.finditer(line):
            word = match.group()
            gap = line[previous_end : match.start()].strip()
            if gap:
                at_start = gap[-1] in ".!?:"
            previous_end = match.end()
            if not word.isdigit():
                key = fold(word).lower()
                self._exact[key][word] += 1
                if not at_start:
                    (self._capitalized if word[0].isupper() else self._lowercase)[key] += 1
            at_start = False

    def restore(self, word: str) -> str:
        key = fold(word).lower()
        if key not in self._exact:
            return word
        spellings: Counter[str] = Counter()
        for form, count in self._exact[key].items():
            spellings[form.lower()] += count
        best, best_count = spellings.most_common(1)[0]
        # slowo bez polskich znakow tez istnieje ("ze", "opieka") - zostaje
        if spellings[word.lower()] >= PLAIN_SHARE * best_count:
            best = word.lower()
        exact = next(form for form, _ in self._exact[key].most_common() if form.lower() == best)
        if any(c.isupper() for c in exact[1:]):
            return exact
        return _capitalize(best) if self._capitalized[key] > self._lowercase[key] else best


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def humanize(slug: str, vocabulary: Vocabulary) -> str:
    """Segment adresu jako czytelny tekst: "siedziba-wydzialu" -> "Siedziba Wydziału"."""
    words = [_TRAILING_NUMBER.sub("", w) or w for w in _SLUG_SPLIT.split(unquote_plus(slug)) if w]
    return _capitalize(" ".join(vocabulary.restore(w) for w in words))


def file_title(name: str, vocabulary: Vocabulary) -> str:
    """Nazwa pliku bez rozszerzenia: "urlop+dzieka%C5%84ski.pdf" -> "Urlop dziekański"."""
    name = unquote_plus(name)
    stem, extension = posixpath.splitext(name)
    if extension.lower() in FILE_EXTENSIONS:
        name = stem
    words = [w for w in re.split(r"[_\s]+", name) if w]
    return _capitalize(" ".join(vocabulary.restore(w) if "-" not in w else w for w in words))


def first_line_title(text: str) -> str:
    """Pierwsza linia tresci jako tytul; dluga linia - pierwsze zdanie,
    obciete do MAX_TITLE znakow na granicy slowa."""
    line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(line) <= MAX_TITLE:
        return line
    sentence = _SENTENCE_END.split(line, maxsplit=1)[0]
    if len(sentence) <= MAX_TITLE:
        return sentence
    return sentence[:MAX_TITLE].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s and s.lower() not in LANG_SEGMENTS]


def _document_name(segments: list[str]) -> str:
    """Nazwa pliku w adresie: segment z rozszerzeniem albo (Liferay)
    /documents/<grupa>/<folder>/<nazwa>/<uuid>."""
    for segment in segments:
        if posixpath.splitext(unquote_plus(segment))[1].lower() in FILE_EXTENSIONS:
            return segment
    if len(segments) >= 4 and segments[0] == "documents":
        return segments[3]
    return segments[-1] if segments else ""


def page_title(url: str, text: str, category: str, is_document: bool, vocabulary: Vocabulary) -> PageTitle:
    parts = urlsplit(url)
    host = parts.netloc
    segments = _segments(parts.path)
    prefix = [host] if category in HOST_PREFIXED else []

    if host == WIKIPEDIA_HOST and len(segments) >= 2 and segments[0] == "wiki":
        title = unquote_plus(segments[1]).replace("_", " ")
        return PageTitle(title, ["Wikipedia", title])
    if is_document:
        return PageTitle(file_title(_document_name(segments), vocabulary), prefix)
    if NEWS_MARKER in segments:
        section = segments[: segments.index("-")] if "-" in segments else []
        title = first_line_title(text)
        return PageTitle(title, [*prefix, *(humanize(s, vocabulary) for s in section), title])
    if not segments:
        line = first_line_title(text)
        title = line if line and len(line) < MAX_TITLE and not line.endswith(("…", ".", "!", "?")) else host
        return PageTitle(title, list(dict.fromkeys([*prefix, title])))

    crumbs = [humanize(s, vocabulary) for s in segments]
    return PageTitle(crumbs[-1], [*prefix, *crumbs])
