"""Zbior pytan (questions.jsonl): wczytanie i sprawdzenie formatu."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import targets

QUESTIONS_FILE = Path(__file__).with_name("questions.jsonl")
LANGS = ("pl", "en")


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    lang: str
    question: str
    # cele z targets.py; pusto = w danych nie ma odpowiedzi (albo poza zakresem)
    expected: tuple[str, ...]
    # wczesniejsze pytania uzytkownika (dopytania), od najstarszego
    history: tuple[str, ...] = field(default=())
    note: str = ""

    @property
    def answerable(self) -> bool:
        return bool(self.expected)


def _parse(line: str, number: int) -> Question:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as error:
        raise ValueError(f"linia {number}: {error}") from None
    try:
        question = Question(
            id=raw["id"],
            category=raw["category"],
            lang=raw["lang"],
            question=raw["question"],
            expected=tuple(raw["expected"]),
            history=tuple(raw.get("history", ())),
            note=raw.get("note", ""),
        )
    except KeyError as error:
        raise ValueError(f"linia {number}: brak pola {error}") from None
    if question.lang not in LANGS:
        raise ValueError(f"linia {number}: jezyk {question.lang!r} spoza {LANGS}")
    for target in question.expected:
        try:
            targets.validate(target)
        except ValueError as error:
            raise ValueError(f"linia {number} ({question.id}): {error}") from None
    return question


def load_questions(path: Path = QUESTIONS_FILE) -> list[Question]:
    questions = [
        _parse(line, number)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if line.strip()
    ]
    ids = [q.id for q in questions]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"powtorzone id: {', '.join(duplicates)}")
    return questions
