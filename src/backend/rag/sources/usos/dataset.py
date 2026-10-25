"""Format zbioru USOS (data/usos/) - rekordy kilku rodzajow rozroznianych po `kind`.

Pracownik (`staff`) ma wszystko w `attributes` i karte budowana przez RAG
(documents.py). Pozostale rodzaje maja tresc w Markdownie (`content`, z
naglowkami - dziela ja na fragmenty) i w `attributes` tylko pola do
metadanych i zrodel odpowiedzi.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ...core.datasets import Record


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- pracownik -------------------------------------------------------------------------

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
    # strona USOSweb z adresem, gdy osoba ukryla go przed robotami (captcha) - email pusty
    email_url: str = ""
    phones: list[str] = Field(default_factory=list)
    homepage_url: str = ""


class StaffRecord(Record):
    """Pracownik; id = id osoby w USOS, title = imie i nazwisko, url = profil
    w USOSweb. Rekord bez tresci - wszystko jest w attributes."""

    kind: Literal["staff"]
    attributes: StaffAttributes


# --- rekordy z trescia -----------------------------------------------------------------

class _ContentRecord(Record):
    # tresc w Markdownie - wymagana
    content: str = Field(min_length=1)


class NewsAttributes(_Strict):
    # id artykulu w USOS
    news_id: str = Field(min_length=1)
    category: str = ""
    # jednostka, ktora opublikowala artykul
    faculty: str = ""
    # do kiedy artykul jest aktualny (None = bez terminu)
    expiry_date: date | None = None


class NewsRecord(_ContentRecord):
    """Artykul z aktualnosci USOSweb; id = news:<id>, updated_at = data publikacji."""

    kind: Literal["news"]
    attributes: NewsAttributes


class PageAttributes(_Strict):
    # host, np. www.usosweb.uj.edu.pl
    site: str = Field(min_length=1)
    # strony informacyjne USOSweb (Dokumenty, Kontakt)
    section: Literal["usosweb"]
    # sciezka w menu, np. ["Dokumenty", "mLegitymacja"]
    breadcrumbs: list[str] = Field(default_factory=list)


class PageRecord(_ContentRecord):
    """Strona informacyjna; id = adres strony, url wymagany."""

    kind: Literal["page"]
    url: str
    attributes: PageAttributes


class UnitAttributes(_Strict):
    # id jednostki w USOS, np. UJ.WMI.II
    fac_id: str = Field(min_length=1)
    # jednostka nadrzedna ("" dla najwyzszej)
    parent_id: str = ""


class UnitRecord(_ContentRecord):
    """Jednostka organizacyjna (wydzial, instytut, katedra); id = unit:<fac_id>."""

    kind: Literal["unit"]
    attributes: UnitAttributes


class CourseAttributes(_Strict):
    # kod przedmiotu w USOS, np. WMI.II-AM1-O
    course_id: str = Field(min_length=1)
    # aktywne cykle dydaktyczne, w ktorych przedmiot jest prowadzony (np. 26/27Z)
    term_ids: list[str] = Field(default_factory=list)
    # jednostka prowadzaca
    fac_id: str = ""
    ects: float | None = None
    # prowadzacy zajecia (imie i nazwisko) w tych cyklach
    lecturers: list[str] = Field(default_factory=list)


class CourseRecord(_ContentRecord):
    """Przedmiot z jego zajeciami w aktywnych cyklach (grupy, prowadzacy,
    terminy i sale); id = course:<kod>."""

    kind: Literal["course"]
    attributes: CourseAttributes


class ProgrammeAttributes(_Strict):
    # id programu studiow w USOS, np. WMI-n037-0-ZD-6
    programme_id: str = Field(min_length=1)
    fac_id: str = ""
    level: str = ""
    mode: str = ""
    duration: str = ""


class ProgrammeRecord(_ContentRecord):
    """Program studiow (kierunek); id = programme:<id>."""

    kind: Literal["programme"]
    attributes: ProgrammeAttributes


class CalendarAttributes(_Strict):
    # rok akademicki, np. 2026/27
    academic_year: str = Field(min_length=1)
    # jednostka, ktorej kalendarz dotyczy
    fac_id: str = ""
    start_date: date
    end_date: date


class CalendarRecord(_ContentRecord):
    """Rok akademicki: semestry, przerwy, sesje i dni wolne;
    id = calendar:<rok>:<jednostka>."""

    kind: Literal["calendar"]
    attributes: CalendarAttributes


class RegistrationAttributes(_Strict):
    # id rejestracji w USOS
    registration_id: str = Field(min_length=1)
    fac_id: str = ""
    # zwykla (na przedmioty) albo zetonowa
    registration_type: Literal["course", "token"] = "course"
    # najwczesniejszy poczatek i najpozniejszy koniec tur
    start_date: date | None = None
    end_date: date | None = None


class RegistrationRecord(_ContentRecord):
    """Rejestracja z turami (terminy, tryb) i przedmiotami do wyboru;
    id = registration:<id>."""

    kind: Literal["registration"]
    attributes: RegistrationAttributes


class BuildingAttributes(_Strict):
    # id budynku w USOS, np. Loj6
    building_id: str = Field(min_length=1)
    campus: str = ""
    address: str = ""
    # jednostki z tego budynku
    fac_ids: list[str] = Field(default_factory=list)


class BuildingRecord(_ContentRecord):
    """Budynek UJ (adres, kampus), dla budynkow wydzialu takze sale;
    id = building:<id>."""

    kind: Literal["building"]
    attributes: BuildingAttributes


class DormitoryAttributes(_Strict):
    dormitory_id: str = Field(min_length=1)


class DormitoryRecord(_ContentRecord):
    """Dom studencki UJ; id = dormitory:<id>."""

    kind: Literal["dormitory"]
    attributes: DormitoryAttributes


UsosRecord = Annotated[
    Union[
        StaffRecord,
        NewsRecord,
        PageRecord,
        UnitRecord,
        CourseRecord,
        ProgrammeRecord,
        CalendarRecord,
        RegistrationRecord,
        BuildingRecord,
        DormitoryRecord,
    ],
    Field(discriminator="kind"),
]

USOS_RECORD = TypeAdapter(UsosRecord)
