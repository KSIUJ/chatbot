"""
Przedmioty prowadzone w aktywnych cyklach: opis z sylabusa, punkty ECTS,
a dla kazdej edycji (cyklu) grupy zajeciowe z prowadzacymi, terminem i sala.

Lista przedmiotow pochodzi z edycji prowadzonych przez pracownikow wydzialu
(ctx.course_editions z kolektora staff - stad zaleznosc od klucza aplikacji;
z tego samego zrodla sa prowadzacy edycji bez planu); same dane
przedmiotow, grup i planu sa dostepne bez klucza:
- courses/course - opis, efekty, kryteria, literatura, ECTS, cykle,
- courses/course_edition2 - opis, literatura i uwagi edycji (tu zwykle jest
  wlasciwy sylabus - opis przedmiotu bywa pusty),
- tt/course_edition - plan zajec (najwyzej 7 dni na zapytanie - brane sa
  dwa niepuste tygodnie od poczatku zajec albo od dzisiaj; cyklicznosc podaje USOS),
- groups/groups - prowadzacy grup (bez list uczestnikow).

Jeden rekord na przedmiot: sekcje sylabusa i sekcja "Zajecia: <cykl>" na
kazda aktywna edycje. Ustala ctx.teaching_buildings (budynki z planu).

Prowadzacy grup spoza listy pracownikow wydzialu (np. fizyk uczacy fizyki
na WMI) dostaja karte jak pracownik (rodzaj `lecturer`, users/users z kluczem
aplikacji) - tylko obecni pracownicy UJ ze stanowiskiem (tez na umowe
cywilnoprawna), bez doktorantow i studentow (ich danych nie zbieramy).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.backend.rag.sources.usos.dataset import CourseAttributes, CourseRecord, LecturerRecord

import logging

from ..api import UsosError, fields
from ..context import Context, Term
from .staff import USER_FIELDS, staff_record
from ..text import (
    document, format_date, frequency, join_nonempty, parse_datetime, pick, pick_markdown, section, weekday,
)

logger = logging.getLogger("usos")

NAME = "courses"
NEEDS_CONSUMER = False

COURSE_FIELDS = fields(
    "id", "name", "profile_url", "homepage_url", "fac_id", "lang_id", "ects_credits_simplified", "terms",
    "description", "bibliography", "learning_outcomes", "assessment_criteria",
)
EDITION_FIELDS = fields("homepage_url", "description", "bibliography", "notes")
TT_FIELDS = fields(
    "start_time", "end_time", "unit_id", "group_number", "classtype_name", "building_id",
    "building_name", "room_number", "frequency",
)
GROUP_FIELDS = fields("course_unit_id", "group_number", "class_type", "lecturers")
# karta prowadzacego spoza wydzialu - pola karty pracownika i statusy studenta
LECTURER_FIELDS = fields(
    *(name for name in USER_FIELDS.split("|") if name != "course_editions_conducted"),
    "student_status", "phd_student_status",
)
ACTIVE_STUDENT = 2
# staff_status: 1 = pracownik (np. umowa cywilnoprawna), 2 = nauczyciel akademicki
EMPLOYED = (1, 2)
LANGUAGES = {"PL": "polski", "EN": "angielski", "DE": "niemiecki", "FR": "francuski", "ES": "hiszpański"}
# ile niepustych tygodni planu zbierac na edycje (zajecia co dwa tygodnie wymagaja dwoch)
TT_WEEKS = 2
TT_MAX_WEEKS = 4
# nazwiska z tytulami po przecinku ("dr hab. Jan Kowalski, prof. UJ") - lista srednikami
LECTURER_SEPARATOR = "; "


@dataclass
class Slot:
    """Jeden termin zajec grupy w tygodniu."""

    weekday: str
    start: str
    end: str
    room: str
    building: str
    frequency: str

    def describe(self) -> str:
        place = join_nonempty([f"sala {self.room}" if self.room else "", self.building])
        return join_nonempty([f"{self.weekday} {self.start}–{self.end}", self.frequency, place])


@dataclass
class Group:
    unit_id: str
    number: int
    classtype: str = ""
    lecturers: list[str] = field(default_factory=list)
    slots: list[Slot] = field(default_factory=list)
    lecturer_ids: list[str] = field(default_factory=list)


def _course_ids(ctx: Context) -> list[str]:
    return sorted({course_id for course_id, _term in ctx.course_editions})


def _tt_start(term: Term, today: date) -> date:
    """Poczatek okna planu: poniedzialek tygodnia, w ktorym zaczynaja sie zajecia,
    biezacego, jesli cykl trwa, albo pierwszego tygodnia cyklu juz zakonczonego
    (przebieg w sesji - plan semestru nadal jest w USOS)."""
    start = term.start if today > term.end else max(term.start, today)
    return start - timedelta(days=start.weekday())


def _timetable(ctx: Context, course_id: str, term: Term) -> list[dict]:
    """Zajecia z TT_WEEKS niepustych tygodni (najwyzej TT_MAX_WEEKS zapytan) -
    tydzien bez zajec (przerwa swiateczna, dni wolne) nie gubi grup. Cykl, ktory
    sie jeszcze nie zaczal i nie ma planu w dwoch pierwszych tygodniach, jest
    pomijany po dwoch zapytaniach (plan powstaje zwykle tuz przed semestrem)."""
    activities: list[dict] = []
    start = _tt_start(term, ctx.today)
    future = term.start > ctx.today
    full_weeks = 0
    for week in range(TT_MAX_WEEKS):
        day = start + timedelta(days=7 * week)
        if day > term.end or full_weeks == TT_WEEKS or (future and week == 2 and not activities):
            break
        got = ctx.api.call(
            "services/tt/course_edition",
            course_id=course_id, term_id=term.id, start=day.isoformat(), days=7, fields=TT_FIELDS,
        )
        found = [a for a in got or [] if isinstance(a, dict)]
        full_weeks += bool(found)
        activities.extend(found)
    return activities


def _groups(ctx: Context, activities: list[dict]) -> dict[tuple[str, int], Group]:
    groups: dict[tuple[str, int], Group] = {}
    for activity in activities:
        unit_id, number = activity.get("unit_id"), activity.get("group_number")
        start, end = parse_datetime(activity.get("start_time")), parse_datetime(activity.get("end_time"))
        if unit_id is None or number is None or start is None or end is None:
            continue
        key = (str(unit_id), int(number))
        group = groups.setdefault(key, Group(str(unit_id), int(number), pick(activity.get("classtype_name"))))
        slot = Slot(
            weekday=weekday(start.date()),
            start=start.strftime("%H:%M"),
            end=end.strftime("%H:%M"),
            room=str(activity.get("room_number") or "").strip(),
            building=pick(activity.get("building_name")),
            frequency=frequency(activity.get("frequency")),
        )
        # te same zajecia w kolejnym tygodniu - jeden termin
        if all(slot.describe() != s.describe() for s in group.slots):
            group.slots.append(slot)
        if activity.get("building_id"):
            ctx.teaching_buildings.add(str(activity["building_id"]))
    return groups


def _add_lecturers(ctx: Context, groups: dict[tuple[str, int], Group]) -> None:
    if not groups:
        return
    pairs = [f"({unit},{number})" for unit, number in groups]
    try:
        got = ctx.api.batch("services/groups/groups", "group_ids", pairs, fields=GROUP_FIELDS)
    except UsosError as error:
        ctx.warn(f"{NAME}: prowadzacy grup niedostepni ({error})")
        return
    for (unit, number), group in groups.items():
        info = got.get(f"({unit},{number})") or {}
        group.classtype = group.classtype or pick(info.get("class_type"))
        names = []
        for lecturer in info.get("lecturers") or []:
            user_id = str(lecturer.get("id") or lecturer.get("user_id") or "")
            name = ctx.staff.get(user_id) or " ".join(
                p for p in (lecturer.get("first_name"), lecturer.get("last_name")) if p
            )
            if name and name not in names:
                names.append(name)
            if user_id:
                group.lecturer_ids.append(user_id)
        group.lecturers = names


def _card_allowed(user: dict) -> bool:
    """Obecny pracownik UJ ze stanowiskiem - nauczyciel akademicki albo np. wspolpracownik
    na umowie cywilnoprawnej (czesc zajec wydzialu prowadza tacy). Doktoranci zwykle nie maja
    stanowiska (a statusy studenta USOS z samym kluczem aplikacji zwraca jako null),
    wiec bez stanowiska karty nie ma."""
    if user.get("staff_status") not in EMPLOYED:
        return False
    if ACTIVE_STUDENT in (user.get("student_status"), user.get("phd_student_status")):
        return False
    positions = [
        pick((item.get("position") or {}).get("name")).casefold()
        for item in user.get("employment_positions") or [] if isinstance(item, dict)
    ]
    return bool(positions) and not any("doktorant" in name for name in positions)


def lecturer_records(ctx: Context, user_ids: set[str]) -> Iterator[LecturerRecord]:
    """Karty prowadzacych spoza listy pracownikow wydzialu."""
    if not user_ids:
        return
    try:
        users = ctx.api.batch("services/users/users", "user_ids", sorted(user_ids), fields=LECTURER_FIELDS, user=True)
    except UsosError as error:
        ctx.warn(f"{NAME}: karty prowadzacych spoza wydzialu niedostepne ({error})")
        return
    skipped = 0
    for user_id in sorted(user_ids):
        user = users.get(user_id)
        if not isinstance(user, dict) or not _card_allowed(user):
            skipped += 1
            continue
        record = staff_record(ctx, user, kind="lecturer")
        if record is not None:
            yield record
    if skipped:
        logger.info("%s: %d prowadzacych spoza wydzialu bez karty (bez stanowiska, doktoranci)", NAME, skipped)


@dataclass
class Edition:
    term: Term
    edition: dict
    groups: dict[tuple[str, int], Group]
    # prowadzacy edycji wedlug USOS (z kart pracownikow) - gdy plan jeszcze nie
    # powstal, to jedyne zrodlo nazwisk
    conductors: list[str] = field(default_factory=list)

    @property
    def lecturers(self) -> list[str]:
        names = [name for group in self.groups.values() for name in group.lecturers]
        return list(dict.fromkeys(names or self.conductors))


def _edition_section(ctx: Context, course: dict, edition: Edition) -> str:
    """Najpierw grupy (prowadzacy, termin, sala) - o nie najczesciej pytaja,
    potem opis, literatura i uwagi do edycji (bez powtarzania opisu przedmiotu)."""
    term, data = edition.term, edition.edition
    by_type: dict[str, list[Group]] = defaultdict(list)
    for group in sorted(edition.groups.values(), key=lambda g: (g.classtype, g.number)):
        by_type[group.classtype or "Zajęcia"].append(group)
    parts = [f"Cykl {term.name} ({term.id}): {format_date(term.start)} – {format_date(term.end)}."]
    if not by_type:
        future = term.start > ctx.today
        parts.append(f"Plan zajęć tej edycji {'nie jest jeszcze' if future else 'nie jest'} dostępny w USOS.")
        if edition.conductors:
            parts.append(f"Prowadzący: {LECTURER_SEPARATOR.join(edition.conductors)}")
    for classtype, type_groups in by_type.items():
        lines = []
        for group in type_groups:
            who = ", ".join(group.lecturers) or "prowadzący nieustalony"
            if len(group.slots) > 1:
                # kazdy termin w osobnej linii - w jednej model mylil sale miedzy dniami
                lines.append(f"- grupa {group.number}: {who}")
                lines.extend(f"  - {slot.describe()}" for slot in group.slots)
            else:
                when = group.slots[0].describe() if group.slots else "termin nieustalony"
                lines.append(f"- grupa {group.number}: {who}; {when}")
        parts.append(f"### {classtype}\n\n" + "\n".join(lines))
    for title, key in (("Opis zajęć", "description"), ("Literatura", "bibliography"), ("Uwagi", "notes")):
        text = pick_markdown(data.get(key), heading_offset=3)
        if text and text != pick_markdown(course.get(key), heading_offset=3):
            parts.append(f"### {title}\n\n{text}")
    if data.get("homepage_url") and data["homepage_url"] != course.get("homepage_url"):
        parts.append(f"Strona edycji: {data['homepage_url']}")
    return section(f"Zajęcia: {term.name}", "\n\n".join(parts))


def course_record(ctx: Context, course: dict, editions: list[Edition]) -> CourseRecord | None:
    course_id = str(course.get("id") or "")
    name = pick(course.get("name"))
    if not course_id or not name:
        return None
    ects = course.get("ects_credits_simplified")
    language = LANGUAGES.get(str(course.get("lang_id") or "").upper(), "")
    terms = [edition.term for edition in editions]
    lecturers = sorted({n for edition in editions for n in edition.lecturers})
    info = [
        f"- Kod przedmiotu: {course_id}",
        f"- Jednostka prowadząca: {ctx.unit_names.get(course['fac_id'], course['fac_id'])}" if course.get("fac_id") else "",
        f"- Punkty ECTS: {ects:g}" if isinstance(ects, (int, float)) else "",
        f"- Język prowadzenia: {language}" if language else "",
        "- Prowadzony w cyklach: " + ", ".join(f"{t.name} ({t.id})" for t in terms) if terms else "",
        f"- Strona przedmiotu: {course['homepage_url']}" if course.get("homepage_url") else "",
        f"- Prowadzący: {LECTURER_SEPARATOR.join(lecturers)}" if lecturers else "",
    ]
    content = document(
        f"# {name} ({course_id})",
        section("Informacje", "\n".join(line for line in info if line)),
        section("Opis", pick_markdown(course.get("description"))),
        section("Efekty uczenia się", pick_markdown(course.get("learning_outcomes"))),
        section("Kryteria oceniania", pick_markdown(course.get("assessment_criteria"))),
        section("Literatura", pick_markdown(course.get("bibliography"))),
        *(_edition_section(ctx, course, edition) for edition in editions),
    )
    return CourseRecord(
        id=f"course:{course_id}",
        kind="course",
        title=f"{name} ({course_id})",
        url=course.get("profile_url") or ctx.usosweb("katalog2/przedmioty/pokazPrzedmiot", prz_kod=course_id),
        lang="pl",
        content=content,
        attributes=CourseAttributes(
            course_id=course_id,
            term_ids=[t.id for t in terms],
            fac_id=str(course.get("fac_id") or ""),
            ects=float(ects) if isinstance(ects, (int, float)) else None,
            lecturers=lecturers,
        ),
    )


def _edition(ctx: Context, course_id: str, term: Term) -> Edition:
    """Edycja przedmiotu w cyklu; blad planu albo opisu edycji nie odrzuca
    przedmiotu - edycja jest wtedy bez tej czesci."""
    conductors = sorted(
        ctx.staff[user_id] for user_id in ctx.course_editions.get((course_id, term.id), ()) if user_id in ctx.staff
    )
    try:
        data = ctx.api.call(
            "services/courses/course_edition2", course_id=course_id, term_id=term.id, fields=EDITION_FIELDS
        ) or {}
    except UsosError as error:
        ctx.warn(f"{NAME}: {course_id} {term.id}: opis edycji niedostepny ({error})")
        data = {}
    try:
        groups = _groups(ctx, _timetable(ctx, course_id, term))
    except UsosError as error:
        ctx.warn(f"{NAME}: {course_id} {term.id}: plan niedostepny ({error})")
        groups = {}
    _add_lecturers(ctx, groups)
    return Edition(term, data, groups, conductors)


def collect(ctx: Context) -> Iterator[CourseRecord | LecturerRecord]:
    course_ids = _course_ids(ctx)
    if not course_ids:
        raise RuntimeError("brak edycji przedmiotow - kolektor staff nie zebral course_editions_conducted")
    terms = {term.id: term for term in ctx.active_terms}
    failures = 0
    skipped_other = 0
    outside: set[str] = set()
    for course_id in course_ids:
        try:
            course = ctx.api.call("services/courses/course", course_id=course_id, fields=COURSE_FIELDS)
            course_terms = {t.get("id") for t in course.get("terms") or [] if isinstance(t, dict)}
            editions = [
                _edition(ctx, course_id, terms[term_id])
                for term_id in sorted(course_terms & set(terms), key=lambda t: terms[t].start)
            ]
        except UsosError as error:
            failures += 1
            ctx.warn(f"{NAME}: {course_id} pominiety ({error})")
            continue
        fac_id = str(course.get("fac_id") or "")
        if fac_id and not ctx.in_faculty(fac_id):
            # przedmiot innego wydzialu prowadzony przez nasza osobe (np. matematyka na
            # chemii) - nie dla studentow WMI, a w wyszukiwaniu zaglusza wlasciwe przedmioty
            skipped_other += 1
            continue
        record = course_record(ctx, course, editions)
        if record is not None:
            outside.update(
                user_id for edition in editions for group in edition.groups.values()
                for user_id in group.lecturer_ids if user_id not in ctx.staff
            )
            yield record
    if skipped_other:
        logger.info("%s: %d przedmiotow innych wydzialow pominietych", NAME, skipped_other)
    if failures > len(course_ids) // 2:
        raise RuntimeError(f"za duzo bledow przedmiotow: {failures}/{len(course_ids)}")
    yield from lecturer_records(ctx, outside)
