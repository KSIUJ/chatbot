"""
Notatki o KSI pisane recznie: pliki Markdown w knowledge/ksi/ (w repo, wiec
tylko informacje publiczne). Kazdy plik zaczyna sie naglowkiem YAML:

    ---
    title: Jak dolaczyc do KSI
    updated: 2026-10-01
    tags: [czlonkostwo]
    url: https://ksi.ii.uj.edu.pl/   # opcjonalnie
    always_include: false            # opcjonalnie
    draft: true                      # opcjonalnie - szkic nie trafia do indeksu
    ---
    Tresc w Markdownie...

README.md i pliki zaczynajace sie od "_" (np. szablon) sa pomijane.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path

import yaml
from pydantic import ValidationError

from ...core.datasets import DatasetError
from .dataset import NoteAttributes, NoteRecord

KNOWLEDGE_DIR = Path(__file__).resolve().parents[5] / "knowledge" / "ksi"
FRONT_MATTER = "---"
_KNOWN_KEYS = {"title", "updated", "tags", "url", "always_include", "draft"}


def _split_front_matter(path: Path, text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER:
        raise DatasetError(f"{path}: brak naglowka YAML (plik musi zaczynac sie od ---)")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == FRONT_MATTER)
    except StopIteration:
        raise DatasetError(f"{path}: niezamkniety naglowek YAML (brak drugiego ---)") from None
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as error:
        raise DatasetError(f"{path}: bledny YAML w naglowku: {error}") from None
    if not isinstance(meta, dict):
        raise DatasetError(f"{path}: naglowek YAML musi byc slownikiem")
    unknown = sorted(set(meta) - _KNOWN_KEYS)
    if unknown:
        raise DatasetError(f"{path}: nieznane pola naglowka: {', '.join(unknown)}")
    return meta, "\n".join(lines[end + 1:]).strip()


def _updated(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    raise ValueError("updated musi byc data RRRR-MM-DD")


def read_note(path: Path) -> NoteRecord | None:
    """Notatka z pliku; None dla szkicu (draft: true).

    Raises:
        DatasetError: brak lub bledny naglowek, brak tytulu albo tresci.
    """
    meta, content = _split_front_matter(path, path.read_text(encoding="utf-8"))
    if meta.get("draft"):
        return None
    if not content:
        raise DatasetError(f"{path}: pusta tresc notatki")
    try:
        return NoteRecord(
            id=path.stem,
            kind="note",
            title=meta.get("title") or "",
            url=meta.get("url"),
            updated_at=_updated(meta.get("updated")),
            content=content,
            attributes=NoteAttributes(tags=meta.get("tags") or [], always_include=bool(meta.get("always_include"))),
        )
    except (ValidationError, ValueError) as error:
        raise DatasetError(f"{path}: {error}") from None


def read_notes(directory: Path = KNOWLEDGE_DIR) -> list[NoteRecord]:
    """Wszystkie gotowe notatki z katalogu (bez README, szablonow i szkicow)."""
    if not directory.is_dir():
        return []
    notes = []
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md" or path.name.startswith("_"):
            continue
        note = read_note(path)
        if note is not None:
            if not note.title:
                raise DatasetError(f"{path}: brak tytulu (title w naglowku)")
            notes.append(note)
    return notes
