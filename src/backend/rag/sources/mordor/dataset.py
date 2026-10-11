"""Format zbioru materialow z Mordoru (data/mordor/: rekordy i pliki)."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...core.datasets import Record


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1)
    text: str
    # tekst z OCR (skan), a nie z warstwy tekstu pliku
    ocr: bool = False


class MaterialAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # sciezka pliku wzgledem data/mordor/ (z "/"), np. "Analiza 1/2024/kolokwium.pdf"
    path: str = Field(min_length=1)
    # rozszerzenie bez kropki: pdf, docx, txt, jpg, png
    file_type: str = Field(min_length=1)
    # przedmiot, rok akademicki ("2024/25") i rodzaj materialu (egzamin,
    # kolokwium, notatki, ...) - puste, gdy nieznane
    course: str = ""
    academic_year: str = ""
    material_kind: str = ""
    # tekst strona po stronie (pdf); pusto = tylko content albo brak tekstu
    pages: list[Page] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def _inside(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("path musi byc wzgledna sciezka z / wewnatrz data/mordor/")
        return value


class MaterialRecord(Record):
    """Plik z Mordoru; id = path. kind: text (jest tekst w content), scan
    (pdf bez warstwy tekstu), image (jpg/png). content = tekst w Markdownie."""

    kind: Literal["text", "scan", "image"]
    attributes: MaterialAttributes
