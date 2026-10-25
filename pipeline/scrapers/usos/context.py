"""Stan jednego przebiegu scrapera, wspolny dla kolektorow.

Kolektor (collectors/<nazwa>.py) to modul z:
- NAME - nazwa (wybor w CLI: --only staff,courses),
- NEEDS_CONSUMER - True, gdy bez klucza aplikacji nie zbierze niczego,
- collect(ctx) -> Iterable[Record] - rekordy formatu usos
  (src/backend/rag/sources/usos/dataset.py).

Kolektory wywolywane sa po kolei (run.COLLECTORS), a pozniejsze moga
korzystac z tego, co wczesniejsze zapisaly w kontekscie (np. przedmioty
z listy pracownikow - ctx.staff).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, tzinfo
from zoneinfo import ZoneInfo

from .api import UsosApi

logger = logging.getLogger("usos")

DEFAULT_FACULTY = "UJ.WMI"
# czasy w USOS API sa lokalne, bez strefy
USOS_TZ = ZoneInfo("Europe/Warsaw")
USOSWEB_URL = "https://www.usosweb.uj.edu.pl/kontroler.php"


@dataclass
class Term:
    id: str
    name: str
    start: date
    end: date


@dataclass
class Context:
    api: UsosApi
    # wydzial, ktorego dane sa zbierane szczegolowo (pracownicy, przedmioty,
    # rejestracje); budynki, akademiki i jednostki - dla calego UJ
    faculty: str = DEFAULT_FACULTY
    # dzisiejsza data w Polsce (kontener ma zwykle UTC)
    today: date = field(default_factory=lambda: datetime.now(USOS_TZ).date())
    lang: str = "pl"
    tz: tzinfo = USOS_TZ
    # --- wypelniane przez kolektory ---
    # wszystkie jednostki wydzialu (faculty i podjednostki)
    faculty_units: list[str] = field(default_factory=list)
    # nazwy jednostek (id -> nazwa) - do opisow przedmiotow i rejestracji
    unit_names: dict[str, str] = field(default_factory=dict)
    # aktywne cykle dydaktyczne (semestry) - collectors/calendar.py
    active_terms: list[Term] = field(default_factory=list)
    # pracownicy wydzialu: id USOS -> imie i nazwisko z tytulami
    staff: dict[str, str] = field(default_factory=dict)
    # edycje przedmiotow prowadzone przez pracownikow: (kod przedmiotu, cykl) -> id prowadzacych
    course_editions: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    # budynki, w ktorych sa zajecia wydzialu (sale z planu) - collectors/places.py
    teaching_buildings: set[str] = field(default_factory=set)
    # klient stron USOSweb (collectors/pages.py); None = kolektor tworzy wlasny
    web: object | None = None
    # ostrzezenia przebiegu (pominiete czesci, bledy pojedynczych obiektow)
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        logger.warning(message)
        self.warnings.append(message)

    def in_faculty(self, fac_id: object) -> bool:
        """Jednostka wydzialu: sam wydzial, jego podjednostka albo jednostka z listy."""
        if not isinstance(fac_id, str) or not fac_id:
            return False
        return fac_id == self.faculty or fac_id.startswith(self.faculty + ".") or fac_id in self.faculty_units

    def usosweb(self, action: str, **params: str) -> str:
        """Adres strony USOSweb, np. usosweb("katalog2/przedmioty/pokazPrzedmiot", prz_kod="...")."""
        from urllib.parse import urlencode

        return f"{USOSWEB_URL}?{urlencode({'_action': action, **params}, safe='/')}"
