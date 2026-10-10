"""Systemy pod testem: kazdy zamienia pytanie na uporzadkowana liste trafien
(cele z rag_eval/targets.py) w kolejnosci, w jakiej trafiaja do kontekstu."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..questions import Question


@dataclass(frozen=True)
class Retrieval:
    # cele kazdego trafienia, w kolejnosci kontekstu
    hits: list[frozenset[str]]
    # dlugosc kontekstu wyslanego do modelu (znaki)
    context_chars: int
    # zapytanie uzyte do wyszukiwania (po ewentualnym przepisaniu dopytania)
    query: str


class System(Protocol):
    name: str

    def retrieve(self, question: Question) -> Retrieval: ...


def _current() -> System:
    from .current import CurrentRag

    return CurrentRag()


# nazwa w --system -> fabryka (import modeli dopiero przy uzyciu)
SYSTEMS: dict[str, Callable[[], System]] = {"current": _current}
