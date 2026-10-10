"""Format informacji o KSI: strony KSI (data/ksi/, jak uj_pages) i notatki
pisane recznie (knowledge/ksi/*.md w repo)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...core.datasets import Record


class NoteAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str] = Field(default_factory=list)
    # dolaczac zawsze, gdy pytanie dotyczy KSI (nie tylko gdy wyszukiwanie ja znajdzie)
    always_include: bool = False


class NoteRecord(Record):
    """Notatka o KSI; id = nazwa pliku bez .md, content = tresc w Markdownie."""

    kind: Literal["note"]
    attributes: NoteAttributes = Field(default_factory=NoteAttributes)
