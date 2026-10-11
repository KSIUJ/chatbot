"""
Wyszukiwarka pracownikow: slownik imion i nazwisk z USOS (z formami
odmiany - names.py) + BM25 zawezony do zrodla usos.

Zapytanie dotyczy pracownika, gdy zawiera nazwisko z USOS:
- w formie podstawowej ("pokoj Moczurad", "Czym zajmuje sie Marcin Kozik"),
- albo w formie odmienionej ("dyzury Debeckiego") lub bedace zwyklym slowem
  (names.COMMON_WORDS: "pogoda", "tutaj"), ale wtedy z dodatkowym sladem
  osoby: imieniem pracownika, tytulem lub slowem o kontakcie (PERSON_WORDS,
  PERSON_PREFIXES) albo wielka litera w srodku zdania.
"""

from __future__ import annotations

import re

from ...core.lexical import LexicalIndex, fold
from .names import COMMON_WORDS, inflected_forms, is_female

DEFAULT_LIMIT = 2

# tytuly i slowa, przy ktorych odmienione nazwisko na pewno dotyczy osoby
# (bez polskich znakow): cale slowa i poczatki slow
PERSON_WORDS = {"dr", "prof", "mgr", "hab", "inz", "pan", "pani", "pana", "panu", "panem", "kim", "kto"}
PERSON_PREFIXES = (
    "doktor", "profesor", "dziekan", "prodziekan", "kierownik", "promotor", "adiunkt", "wykladowc",
    "dyzur", "konsultac", "pokoj", "gabinet", "mail", "telefon", "kontakt", "prowadz", "zajmuje",
)
_WORD = re.compile(r"\w+", re.UNICODE)


class StaffIndex:
    def __init__(self, names: list[str], lexical: LexicalIndex):
        self.lexical = lexical
        self.name_tokens: set[str] = set()
        self.surnames: set[str] = set()
        # forma odmieniona -> tokeny imion/nazwisk, od ktorych pochodzi
        self._forms: dict[str, set[str]] = {}

        declined: set[str] = set()
        for name in names:
            parts = _tokens(name or "")
            if not parts:
                continue
            self.name_tokens.update(parts)
            self.surnames.update(parts[1:] or parts)
            declined.update(_declined_tokens(parts))

        for token in declined:
            for form in inflected_forms(token):
                if form not in self.name_tokens:
                    self._forms.setdefault(form, set()).add(token)

    @classmethod
    def from_collection(cls, collection, lexical: LexicalIndex) -> StaffIndex:
        got = collection.get(where={"source": "usos"}, include=["metadatas"])
        names = [(m or {}).get("employee_name") or "" for m in got.get("metadatas", [])]
        return cls(names, lexical)

    def _first_name(self, token: str) -> bool:
        return token in self.name_tokens and token not in self.surnames

    def _person_context(self, words: list[str], base: list[str], positions: list[int]) -> bool:
        """Slad osoby obok odmienionego nazwiska: imie pracownika (tez
        odmienione), tytul albo slowo o kontakcie, albo nazwisko wielka
        litera nie na poczatku zapytania."""
        for token in base:
            if self._first_name(token) or any(self._first_name(c) for c in self._forms.get(token, ())):
                return True
            if token in PERSON_WORDS or token.startswith(PERSON_PREFIXES):
                return True
        return any(i > 0 and words[i][:1].isupper() for i in positions)

    def lookup(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        words = _WORD.findall(query)
        base = [fold(word).lower() for word in words]

        exact = [token for token in base if token in self.name_tokens]
        inflected = [sorted(self._forms.get(token, ())) for token in base]
        # pozycje odmienionych nazwisk (wielka litera w srodku zdania to slad osoby;
        # nie dla nazwisk-zwyklych slow - "Polak", "Niemiec" pisze sie wielka)
        positions = [i for i, canon in enumerate(inflected) if self.surnames.intersection(canon)]
        ambiguous = any(token in self.surnames and token in COMMON_WORDS for token in base)

        found = any(token in self.surnames and token not in COMMON_WORDS for token in exact)
        if not found and (positions or ambiguous):
            found = self._person_context(words, base, positions)
        if not found:
            return []

        matched = list(dict.fromkeys(exact + [c for canon in inflected for c in canon]))
        return self.lexical.search(matched, sources=("usos",), limit=limit)


def _declined_tokens(parts: list[str]) -> list[str]:
    """Tokeny imienia i nazwiska, ktore sie odmieniaja: nazwiska kobiet na
    spolgloske albo -o sa nieodmienne (Ewa Cygan, Anna Gron)."""
    if len(parts) < 2 or not is_female(parts[0]):
        return parts
    return [parts[0]] + [token for token in parts[1:] if token.endswith("a")]


def _tokens(text: str) -> list[str]:
    return [fold(word).lower() for word in _WORD.findall(text)]
