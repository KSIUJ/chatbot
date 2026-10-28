"""Srednie ocen osoby z danych USOS (narzedzie usos_my_averages w tools.py) -
liczone tu, nie przez model, ktory myli sie w dlugich rachunkach.

Zasady (opisane tez w wyniku, zeby model mogl je wyjasnic):
- licza sie oceny, ktore USOS oznacza jako wliczane do sredniej
  (counts_into_average), ze wszystkich terminow - takze niedostateczne
  i poprawkowe; oceny opisowe (np. "zal") sa pomijane,
- srednia zwykla i wazona punktami ECTS przedmiotu,
- rok akademicki z kodu cyklu (24/25Z, 24/25L, 24/25 -> 2024/25), rok
  studiow - wzgledem roku przyjecia na kierunek.

Przypisanie przedmiotu do kierunku: USOS API (bez klucza administracyjnego)
podaje powiazanie przedmiotu z kierunkiem tylko dla przedmiotow z rejestracji
w biezacych cyklach (registrations/courses_cart, pole links). Wczesniejsze
przedmioty sa przypisywane, gdy w tym roku akademickim trwal tylko jeden
kierunek z zaliczonymi punktami (credits/used_sum > 0); pozostale wynik
podaje osobno jako nieprzypisane, z kierunkami, do ktorych moga nalezec.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

METHOD = (
    "Średnia z ocen, które USOS oznacza jako wliczane do średniej, ze wszystkich terminów (także niedostatecznych "
    "i poprawkowych), bez ocen opisowych; ważona: każda ocena z wagą punktów ECTS przedmiotu. To szacunek - "
    "oficjalna średnia jest w USOSweb. Przedmioty bez pewnego kierunku są w unassigned_courses."
)


@dataclass(frozen=True)
class GradeEntry:
    term: str
    course_id: str
    value: float
    # numer terminu (1 = pierwszy, 2 = poprawka...)
    session: int | None = None


@dataclass(frozen=True)
class Programme:
    # id programu osoby (student_programme) i kod programu (np. WMI-0037-1SO)
    id: str
    code: str
    name: str
    status: str
    admission: date | None
    # ECTS zaliczone na kierunku wg USOS (credits/used_sum); None = nieznane
    ects_used: float | None = None

    @property
    def start_year(self) -> int | None:
        """Pierwszy rok akademicki kierunku (przyjecie we wrzesniu albo pozniej = ten rok)."""
        if self.admission is None:
            return None
        return self.admission.year if self.admission.month >= 8 else self.admission.year - 1


@dataclass
class Stats:
    values: list[float] = field(default_factory=list)
    weighted: list[tuple[float, float]] = field(default_factory=list)

    def add(self, value: float, ects: float | None) -> None:
        self.values.append(value)
        if ects:
            self.weighted.append((value, ects))

    def summary(self) -> dict[str, Any]:
        if not self.values:
            return {"average": None, "weighted_average": None, "grades": 0, "ects": 0}
        ects = sum(weight for _value, weight in self.weighted)
        return {
            "average": round(sum(self.values) / len(self.values), 2),
            "weighted_average": round(sum(v * w for v, w in self.weighted) / ects, 2) if ects else None,
            "grades": len(self.values),
            "ects": _number(ects),
        }


def grade_value(symbol: object) -> float | None:
    """Ocena liczbowa ("4,5", "5", "3.5", "5!") albo None dla opisowych ("zal", "NK")."""
    text = str(symbol or "").strip().rstrip("!").replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None
    return value if 2 <= value <= 5.5 else None


def counts_into_average(flag: object) -> bool:
    return flag is True or str(flag).upper() in ("T", "TRUE", "Y")


def academic_year(term: str) -> int | None:
    """Pierwszy rok kalendarzowy roku akademickiego z kodu cyklu: 24/25Z -> 2024."""
    try:
        return 2000 + int(term[:2])
    except ValueError:
        return None


def year_label(start: int) -> str:
    return f"{start}/{(start + 1) % 100:02d}"


def parse_year(text: str) -> int | None:
    """2024/25, 2024/2025, 24/25 albo 24/25Z -> 2024."""
    head = text.strip().split("/")[0]
    if head.isdigit():
        return int(head) if len(head) == 4 else 2000 + int(head) if len(head) == 2 else None
    return None


def assign(
    course_id: str, term: str, programmes: Sequence[Programme], links: Mapping[tuple[str, str], set[str]],
) -> tuple[list[Programme], str]:
    """Kierunki przedmiotu w cyklu i sposob przypisania: "link" (z rejestracji),
    "only" (jedyny kierunek z punktami w tym roku), "ambiguous" albo "none"."""
    linked = links.get((term, course_id))
    if linked:
        chosen = [p for p in programmes if p.code in linked]
        if chosen:
            return chosen, "link"
    year = academic_year(term)
    running = [p for p in programmes if year is not None and p.start_year is not None and p.start_year <= year]
    with_credits = [p for p in running if p.ects_used]
    candidates = with_credits or running
    if len(candidates) == 1:
        return candidates, "only"
    return candidates, "ambiguous" if candidates else "none"


def compute_averages(
    grades: Iterable[GradeEntry],
    ects: Mapping[tuple[str, str], float | None],
    names: Mapping[str, str],
    programmes: Sequence[Programme],
    links: Mapping[tuple[str, str], set[str]],
    *,
    programme: str = "",
    year: int | None = None,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> dict[str, Any]:
    """Srednie: ogolem, wg roku akademickiego i wg kierunku (z rokami studiow).

    programme - fragment nazwy albo kod kierunku: tylko jego przedmioty (pewne
    przypisanie) i te z include; year - tylko ten rok akademicki;
    include / exclude - kody przedmiotow dolaczane do wybranego kierunku
    (np. potwierdzone przez osobe) albo pomijane wszedzie."""
    include_set, exclude_set = set(include), set(exclude)
    wanted = programme.strip().casefold()
    selected = [p for p in programmes if not wanted or wanted in p.name.casefold() or wanted in p.code.casefold()]
    overall, by_year = Stats(), {}
    by_programme: dict[str, Stats] = {p.id: Stats() for p in programmes}
    programme_years: dict[tuple[str, int], Stats] = {}
    unassigned: dict[tuple[str, str], list[str]] = {}
    used_courses: set[tuple[str, str]] = set()

    for entry in grades:
        start = academic_year(entry.term)
        if entry.course_id in exclude_set or start is None or (year is not None and start != year):
            continue
        owners, how = assign(entry.course_id, entry.term, programmes, links)
        if wanted and entry.course_id in include_set:
            owners, how = selected, "include"
        certain = how in ("link", "only", "include")
        if wanted:
            # wybrany kierunek: tylko przedmioty pewnie do niego przypisane (albo dolaczone)
            owners = [o for o in owners if o in selected]
            if not owners:
                continue
            if not certain:
                unassigned[(entry.term, entry.course_id)] = [o.name for o in owners]
                continue
        weight = ects.get((entry.term, entry.course_id))
        overall.add(entry.value, weight)
        by_year.setdefault(start, Stats()).add(entry.value, weight)
        used_courses.add((entry.term, entry.course_id))
        if not certain:
            if owners:
                unassigned[(entry.term, entry.course_id)] = [o.name for o in owners]
            continue
        for owner in owners:
            by_programme[owner.id].add(entry.value, weight)
            programme_years.setdefault((owner.id, start), Stats()).add(entry.value, weight)

    shown = selected if wanted else programmes
    return {
        "method": METHOD,
        "filters": {"programme": programme or None, "academic_year": year_label(year) if year else None,
                    "include_courses": sorted(include_set), "exclude_courses": sorted(exclude_set)},
        "overall": overall.summary(),
        "by_academic_year": [{"academic_year": year_label(y), **s.summary()} for y, s in sorted(by_year.items())],
        "by_programme": [
            {
                "programme": p.name, "code": p.code, "status": p.status,
                "admission_date": p.admission.isoformat() if p.admission else "",
                "ects_used_in_usos": p.ects_used,
                **by_programme[p.id].summary(),
                "years": [
                    {"academic_year": year_label(y), "year_of_study": y - p.start_year + 1 if p.start_year else None,
                     **s.summary()}
                    for (pid, y), s in sorted(programme_years.items()) if pid == p.id
                ],
            }
            for p in shown
        ],
        "unassigned_courses": [
            {"term": term, "course_id": cid, "course": names.get(cid, ""), "possible_programmes": owners}
            for (term, cid), owners in sorted(unassigned.items())
        ],
        "courses_counted": len(used_courses),
    }


def _number(value: float) -> float:
    return int(value) if float(value).is_integer() else round(value, 2)
