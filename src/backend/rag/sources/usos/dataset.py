"""Format zbioru pracownikow (data/usos/)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...core.datasets import Record


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(_Strict):
    # nazwa stanowiska, np. "adiunkt"
    name: str = Field(min_length=1)
    # jednostka, np. "Wydział Matematyki i Informatyki"
    unit: str = ""


class Room(_Strict):
    number: str = ""
    building: str = ""


class StaffAttributes(_Strict):
    usos_id: str = Field(min_length=1)
    first_name: str = ""
    last_name: str = Field(min_length=1)
    titles_before: str = ""
    titles_after: str = ""
    positions: list[Position] = Field(default_factory=list)
    room: Room | None = None
    # zwykly tekst (bez HTML-a)
    office_hours: str = ""
    interests: str = ""
    email: str = ""
    phones: list[str] = Field(default_factory=list)
    homepage_url: str = ""


class StaffRecord(Record):
    """Pracownik; id = id osoby w USOS, title = imie i nazwisko, url = profil
    w USOSweb. Rekord bez tresci - wszystko jest w attributes."""

    kind: Literal["staff"]
    attributes: StaffAttributes
