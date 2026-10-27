"""Kolektory USOS na atrapie API: kalendarz, pracownicy, przedmioty z planem,
aktualnosci i rejestracje - rekordy zgodne z formatem usos."""

from __future__ import annotations

from datetime import date

import pytest
from tests.pipeline.usos.fake_usos_api import TERM, consumer_required, context

from pipeline.scrapers.usos.collectors import calendar, courses, news, registrations, staff
from src.backend.rag.sources.usos.dataset import USOS_RECORD


def _valid(records):
    records = list(records)
    for record in records:
        USOS_RECORD.validate_json(record.model_dump_json())
    return records


TERMS = [
    {"id": "26/27Z", "name": {"pl": "Semestr zimowy 2026/2027"}, "start_date": "2026-10-01", "end_date": "2027-01-28",
     "finish_date": "2027-09-30", "order_key": 1},
    {"id": "26/27L", "name": {"pl": "Semestr letni 2026/2027"}, "start_date": "2027-02-26", "end_date": "2027-06-15",
     "finish_date": "2027-09-30", "order_key": 2},
    {"id": "26/27", "name": {"pl": "Rok akademicki 2026/2027"}, "start_date": "2026-10-01", "end_date": "2027-06-15",
     "finish_date": "2027-09-30", "order_key": 3},
]


# --- kalendarz -------------------------------------------------------------------------

def test_calendar_lists_semesters_and_events():
    def events(faculty_id, start_date, end_date, fields):
        if start_date <= "2026-12-23" <= end_date:
            return [{"id": 5, "name": {"pl": "Przerwa świąteczna"}, "start_date": "2026-12-23", "end_date": "2027-01-01",
                     "type": "holidays", "is_day_off": True, "faculty": {"name": {"pl": "UJ"}}},
                    {"id": 6, "name": {"pl": ""}, "start_date": "2026-01-01", "end_date": "2026-12-31", "type": "links_edit"}]
        return []

    ctx = context({"services/terms/terms_index": TERMS, "services/calendar/search": events})

    (record,) = _valid(calendar.collect(ctx))

    assert record.id == "calendar:26/27:UJ.WMI"
    assert record.title == "Kalendarz akademicki 2026/2027 (26/27)"
    assert "| Semestr letni 2026/2027 | 26/27L | 26.02.2027 | 15.06.2027 | 30.09.2027 |" in record.content
    assert "| Przerwa świąteczna | 23.12.2026 – 01.01.2027 | święto | tak | UJ |" in record.content
    assert [t.id for t in ctx.active_terms] == ["26/27Z", "26/27L", "26/27"]
    # okna najwyzej miesieczne, dla UJ i wydzialu
    windows = [p for m, p in ctx.api.calls if m == "services/calendar/search"]
    assert all((date.fromisoformat(p["end_date"]) - date.fromisoformat(p["start_date"])).days <= 30 for p in windows)
    assert {p["faculty_id"] for p in windows} == {"UJ.WMI"}
    assert "links_edit" not in record.content


def test_calendar_without_key_keeps_semesters():
    ctx = context({
        "services/terms/terms_index": TERMS,
        "services/calendar/search": consumer_required("services/calendar/search"),
    }, consumer=False)

    (record,) = _valid(calendar.collect(ctx))

    assert "## Semestry" in record.content and "## Wydarzenia" not in record.content
    assert any("klucza" in w for w in ctx.warnings)


# --- pracownicy ------------------------------------------------------------------------

USERS = {
    "1": {
        "id": "1", "first_name": "Jan", "last_name": "Kowalski", "titles": {"before": "dr hab.", "after": "prof. UJ"},
        "staff_status": 2, "email": None, "phone_numbers": ["12 664 00 00"],
        "office_hours": {"pl": "<p>wtorek <b>10-12</b></p>", "en": ""}, "interests": {"pl": "", "en": "analysis"},
        "room": {"number": "1094", "building_name": {"pl": "III Kampus, budynek WMI"}},
        "employment_positions": [
            {"position": {"name": {"pl": "profesor uczelni"}}, "faculty": {"name": {"pl": "Instytut Matematyki"}}},
            {"position": {"name": {"pl": "profesor uczelni"}}, "faculty": {"name": {"pl": "Instytut Matematyki"}}},
        ],
        "course_editions_conducted": [
            {"course": {"id": "WMI.IM-AM1"}, "term": {"id": "26/27Z"}},
            {"course": {"id": "WMI.OLD"}, "term": {"id": "19/20Z"}},
        ],
        "profile_url": "https://www.usosweb.uj.edu.pl/kontroler.php?_action=katalog2/osoby/pokazOsobe&os_id=1",
    },
    "2": {"id": "2", "first_name": "Ewa", "last_name": "Były", "staff_status": 1},
    "3": {"id": "3", "first_name": "", "last_name": ""},
}


def test_staff_records_and_course_editions():
    ctx = context({
        "services/users/staff_index": {"users": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 1}], "next_page": False},
        "services/users/users": lambda user_ids, fields: {i: USERS[i] for i in user_ids},
    }, faculty_units=["UJ.WMI", "UJ.WMI.IM"], active_terms=[TERM])

    (record,) = _valid(staff.collect(ctx))

    a = record.attributes
    assert (record.id, record.title, a.titles_before, a.titles_after) == ("1", "Jan Kowalski", "dr hab.", "prof. UJ")
    assert a.office_hours == "wtorek 10-12" and a.interests == "analysis"
    assert [p.name for p in a.positions] == ["profesor uczelni"]
    assert a.room.number == "1094" and a.email == ""
    assert ctx.staff == {"1": "dr hab. Jan Kowalski, prof. UJ"}
    assert ctx.course_editions == {("WMI.IM-AM1", "26/27Z"): {"1"}}
    index_call = next(p for m, p in ctx.api.calls if m == "services/users/staff_index")
    assert index_call["fac_ids"] == ["UJ.WMI", "UJ.WMI.IM"]
    assert any("osoba 3 bez nazwiska" in w for w in ctx.warnings)
    # adresy e-mail tylko z tokenem uzytkownika (jesli jest)
    assert all(p.get("user") for m, p in ctx.api.calls if m == "services/users/users")


def test_staff_without_anyone_is_an_error():
    ctx = context({"services/users/staff_index": {"users": [], "next_page": False}}, active_terms=[TERM])

    with pytest.raises(RuntimeError):
        list(staff.collect(ctx))


# --- przedmioty ------------------------------------------------------------------------

COURSE = {
    "id": "WMI.IM-AM1", "name": {"pl": "Analiza matematyczna 1"}, "fac_id": "UJ.WMI.IM", "lang_id": "PL",
    "ects_credits_simplified": 8.0, "terms": [{"id": "26/27Z"}, {"id": "25/26Z"}],
    "description": {"pl": "<p>Granice i <b>ciągłość</b>.</p><script>x()</script>"},
    "learning_outcomes": {"pl": ""}, "assessment_criteria": {"pl": "<ul><li>egzamin</li><li>kolokwia</li></ul>"},
    "bibliography": {"pl": ""}, "homepage_url": "",
    "profile_url": "https://www.usosweb.uj.edu.pl/kontroler.php?_action=katalog2/przedmioty/pokazPrzedmiot&prz_kod=WMI.IM-AM1",
}


def _tt(course_id, term_id, start, days, fields):
    week = {
        "2026-10-19": ["2026-10-20", "2026-10-22"],
        "2026-10-26": ["2026-10-27"],
    }[start]
    out = [{"start_time": f"{week[0]} 10:00:00", "end_time": f"{week[0]} 12:00:00", "unit_id": 11, "group_number": 1,
            "classtype_name": {"pl": "Wykład"}, "building_id": "Loj6", "building_name": {"pl": "budynek WMI"},
            "room_number": "0004", "frequency": "every_week"}]
    if len(week) > 1:
        out.append({"start_time": f"{week[1]} 12:15:00", "end_time": f"{week[1]} 14:00:00", "unit_id": 12, "group_number": 2,
                    "classtype_name": {"pl": "Ćwiczenia"}, "building_id": "Loj6", "building_name": {"pl": "budynek WMI"},
                    "room_number": "1094", "frequency": "every_two_weeks"})
    return out


def test_course_record_with_groups_and_timetable():
    ctx = context({
        "services/courses/course": COURSE,
        "services/courses/course_edition2": {"notes": {"pl": "<p>Zajęcia od 2. tygodnia.</p>"}, "course_units": []},
        "services/tt/course_edition": _tt,
        "services/groups/groups": {
            "(11,1)": {"lecturers": [{"id": "1", "first_name": "Jan", "last_name": "Kowalski"}]},
            "(12,2)": {"lecturers": [{"id": "9", "first_name": "Anna", "last_name": "Nowak"}],
                       "class_type": {"pl": "Ćwiczenia"}},
        },
        # prowadzaca spoza listy pracownikow wydzialu
        "services/users/users": {"9": {"id": "9", "first_name": "Anna", "last_name": "Nowak", "staff_status": 2,
                                       "employment_positions": [{"position": {"name": {"pl": "adiunkt"}},
                                                                 "faculty": {"name": {"pl": "Wydział Fizyki"}}}]}},
    }, active_terms=[TERM], course_editions={("WMI.IM-AM1", "26/27Z"): {"1"}}, staff={"1": "dr hab. Jan Kowalski"},
        unit_names={"UJ.WMI.IM": "Instytut Matematyki"})

    record, lecturer = _valid(courses.collect(ctx))

    content = record.content
    assert record.id == "course:WMI.IM-AM1" and record.title == "Analiza matematyczna 1 (WMI.IM-AM1)"
    assert "- Jednostka prowadząca: Instytut Matematyki" in content
    assert "- Punkty ECTS: 8" in content
    assert "Granice i **ciągłość**." in content and "x()" not in content
    assert "- egzamin\n- kolokwia" in content
    # tylko aktywny cykl, z uwagami i grupami
    assert "## Zajęcia: Semestr zimowy 2026/2027" in content and "25/26Z" not in content
    assert "Zajęcia od 2. tygodnia." in content
    assert "### Wykład\n\n- grupa 1: dr hab. Jan Kowalski; wtorek 10:00–12:00, co tydzień, sala 0004, budynek WMI" in content
    assert "- grupa 2: Anna Nowak; czwartek 12:15–14:00, co dwa tygodnie, sala 1094, budynek WMI" in content
    # ten sam termin w drugim tygodniu nie powtarza sie
    assert content.count("wtorek 10:00–12:00") == 1
    assert record.attributes.lecturers == ["Anna Nowak", "dr hab. Jan Kowalski"]
    assert ctx.teaching_buildings == {"Loj6"}
    assert (lecturer.kind, lecturer.id, lecturer.title) == ("lecturer", "9", "Anna Nowak")
    assert lecturer.attributes.positions[0].unit == "Wydział Fizyki"
    ((_, params),) = [(m, p) for m, p in ctx.api.calls if m == "services/users/users"]
    assert params["user_ids"] == ["9"] and "phd_student_status" in params["fields"]
    # okno planu od poniedzialku biezacego tygodnia (dzis 25.10.2026, niedziela)
    starts = [p["start"] for m, p in ctx.api.calls if m == "services/tt/course_edition"]
    assert starts == ["2026-10-19", "2026-10-26"]


def test_course_failure_is_skipped_with_warning():
    from pipeline.scrapers.usos.api import UsosError

    def course(course_id, fields):
        if course_id == "BAD":
            raise UsosError("services/courses/course", 400, "bad")
        return {**COURSE, "id": course_id, "terms": []}

    ctx = context({"services/courses/course": course}, active_terms=[TERM],
                  course_editions={("BAD", "26/27Z"): set(), ("OK1", "26/27Z"): set(), ("OK2", "26/27Z"): set()})

    records = _valid(courses.collect(ctx))

    assert [r.id for r in records] == ["course:OK1", "course:OK2"]
    assert any("BAD" in w for w in ctx.warnings)
    # zostanie z poprzedniego zbioru
    assert ctx.unrefreshed == {"course:BAD"}


# --- aktualnosci -----------------------------------------------------------------------

def test_news_records():
    article = {
        "id": 77, "title": {"pl": "Stypendium rektora"}, "publication_date": "2026-10-01 08:00:00",
        "expiry_date": "2026-10-15", "content_html": {"pl": "<h2>Terminy</h2><p>Wnioski do <b>15.10</b>.</p>"},
        "category": {"name": {"pl": "Stypendia"}}, "faculty": {"id": "UJ", "name": {"pl": "Uniwersytet Jagielloński"}},
    }
    other = {**article, "id": 78, "faculty": {"id": "UJ.WZ", "name": {"pl": "Wydział Zarządzania"}}}
    ctx = context({"services/news/search": {"items": [{"article": article}, {"article": {"id": 1}}, {"article": other}], "next_page": False}})

    (record,) = _valid(news.collect(ctx))

    assert record.id == "news:77" and record.attributes.expiry_date == date(2026, 10, 15)
    assert record.updated_at.isoformat() == "2026-10-01T08:00:00+02:00"
    assert "Opublikowano: 01.10.2026, 08:00" in record.content
    assert "### Terminy\n\nWnioski do **15.10**." in record.content


# --- rejestracje -----------------------------------------------------------------------

def test_registrations_with_rounds_and_courses():
    registration = {
        "id": "WMI-26/27Z-OG", "description": {"pl": "Ogólnouczelniane 26/27Z"}, "status": "active",
        "faculty": {"id": "UJ.WMI", "name": {"pl": "Wydział Matematyki i Informatyki"}},
        "message": {"pl": "<p>Zapisy w USOSweb.</p>"},
        "rounds": [
            {"id": 10, "name": {"pl": "Tura 1"}, "start_date": "2026-09-20 10:00:00", "end_date": "2026-10-05 23:59:00",
             "registration_mode": "direct_for__courses_and_groups", "status": "closed", "selection_limit": 2},
            {"id": 11, "name": {"pl": "Stara tura"}, "start_date": "2025-09-20 10:00:00", "end_date": "2025-10-05 23:59:00"},
        ],
    }
    ctx = context({
        "services/registrations/faculty_registrations": lambda faculty_id, **_: [registration] if faculty_id == "UJ.WMI" else [],
        "services/registrations/faculty_token_registrations": [],
        "services/registrations/registration_round_courses": [
            {"course": {"id": "WMI.X", "name": {"pl": "Kryptografia"}}, "term_id": "26/27Z", "limits": {"total": 30},
             "registrations_count": 28},
        ],
    }, faculty_units=["UJ.WMI", "UJ.WMI.II"])

    (record,) = _valid(registrations.collect(ctx))

    assert record.id == "registration:WMI-26/27Z-OG"
    assert "| 1 | Tura 1 | 20.09.2026, 10:00 – 05.10.2026, 23:59 | bezpośrednia do przedmiotów i grup (kto pierwszy) | zamknięta | 2 |" in record.content
    assert "Stara tura" not in record.content
    assert "| Kryptografia | WMI.X | 26/27Z | 30 |" in record.content
    assert record.attributes.start_date == date(2026, 9, 20)


def test_staff_needs_active_terms():
    with pytest.raises(RuntimeError, match="cykli"):
        list(staff.collect(context({})))


def test_course_edition_without_plan_and_failing_timetable():
    from pipeline.scrapers.usos.api import UsosError

    summer = TERM.__class__("26/27L", "Semestr letni 2026/2027", date(2027, 2, 26), date(2027, 6, 15))

    def tt(course_id, term_id, start, days, fields):
        if term_id == "26/27Z":
            raise UsosError("services/tt/course_edition", 500, "err")
        return []

    ctx = context({
        "services/courses/course": {**COURSE, "terms": [{"id": "26/27Z"}, {"id": "26/27L"}]},
        "services/courses/course_edition2": lambda course_id, term_id, fields: {
            "description": {"pl": "Sylabus edycji."} if term_id == "26/27L" else {"pl": ""},
        },
        "services/tt/course_edition": tt,
    }, active_terms=[TERM, summer], staff={"1": "dr hab. Jan Kowalski"},
        course_editions={("WMI.IM-AM1", "26/27Z"): {"1"}, ("WMI.IM-AM1", "26/27L"): {"1", "2"}})

    (record,) = _valid(courses.collect(ctx))

    # blad planu zimowego nie odrzuca przedmiotu; letni bez planu - prowadzacy z kart pracownikow
    assert any("plan niedostepny" in w for w in ctx.warnings)
    summer_part = record.content.split("## Zajęcia: Semestr letni 2026/2027")[1]
    assert "Plan zajęć tej edycji nie jest jeszcze dostępny w USOS." in summer_part
    assert "Prowadzący: dr hab. Jan Kowalski" in summer_part
    assert "### Opis zajęć\n\nSylabus edycji." in summer_part
    assert record.attributes.lecturers == ["dr hab. Jan Kowalski"]
    # przyszly cykl bez planu - dwa zapytania, nie cztery
    assert sum(1 for m, p in ctx.api.calls if m == "services/tt/course_edition" and p["term_id"] == "26/27L") == 2


def test_plain_text_fields_keep_paragraphs():
    from pipeline.scrapers.usos.text import pick_markdown

    assert pick_markdown({"pl": "Pierwszy.\r\n\r\nDrugi:\n• a\n• b <3"}) == "Pierwszy.\n\nDrugi:\n• a\n• b <3"
    assert pick_markdown({"pl": "<p>HTML</p>\n<p>x</p>"}) == "HTML\n\nx"


def test_hidden_email_becomes_a_profile_link():
    from src.backend.rag.sources.usos.documents import staff_document

    users = {
        "1": {**USERS["1"], "email": None, "has_email": True,
              "email_url": "https://www.usosweb.uj.edu.pl/kontroler.php?_action=katalog2/osoby/pokazOsobe&focus=email&os_id=1"},
        "4": {"id": "4", "first_name": "Ola", "last_name": "Jawna", "staff_status": 2, "email": "ola@uj.edu.pl",
              "email_url": "https://www.usosweb.uj.edu.pl/x"},
        "5": {"id": "5", "first_name": "Bez", "last_name": "Adresu", "staff_status": 2, "email": None, "has_email": False,
              "email_url": "https://www.usosweb.uj.edu.pl/x"},
    }
    ctx = context({
        "services/users/staff_index": {"users": [{"id": i} for i in users], "next_page": False},
        "services/users/users": lambda user_ids, fields: {i: users[i] for i in user_ids},
    }, faculty_units=["UJ.WMI"], active_terms=[TERM])

    hidden, public, none = _valid(staff.collect(ctx))

    assert (hidden.attributes.email, hidden.attributes.email_url) == ("", users["1"]["email_url"])
    assert (public.attributes.email, public.attributes.email_url) == ("ola@uj.edu.pl", "")
    assert none.attributes.email_url == ""
    card = staff_document("usos", hidden).value
    assert f"E-mail: ukryty przed robotami, widoczny w profilu USOSweb: {users['1']['email_url']}" in card
    assert "E-mail: brak danych w USOS" in staff_document("usos", none).value


def test_group_with_several_slots_lists_each_on_its_own_line():
    from pipeline.scrapers.usos.collectors.courses import Group, Slot, _edition_section, Edition

    group = Group("11", 7, "Ćwiczenia", ["dr Ewa Cygan, prof. UJ"], [
        Slot("poniedziałek", "10:00", "12:00", "1008", "budynek WMI", "co tydzień"),
        Slot("wtorek", "08:00", "10:00", "0116", "budynek WMI", "co tydzień"),
    ])
    text = _edition_section(context({}), {}, Edition(TERM, {}, {("11", 7): group}))

    assert ("- grupa 7: dr Ewa Cygan, prof. UJ\n"
            "  - poniedziałek 10:00–12:00, co tydzień, sala 1008, budynek WMI\n"
            "  - wtorek 08:00–10:00, co tydzień, sala 0116, budynek WMI") in text


def test_lecturers_outside_faculty_without_doctoral_students():
    group_lecturers = [{"id": str(i), "first_name": "X", "last_name": f"L{i}"} for i in range(2, 9)]
    adjunct = [{"position": {"name": {"pl": "adiunkt"}}, "faculty": {"name": {"pl": "Wydział Fizyki"}}}]
    users = {
        # pracownik innego wydzialu - karta
        "2": {"id": "2", "last_name": "L2", "staff_status": 2, "employment_positions": adjunct},
        # doktorant (stanowisko, status doktoranta albo studenta, brak stanowiska) - bez karty
        "3": {"id": "3", "last_name": "L3", "staff_status": 2,
              "employment_positions": [{"position": {"name": {"pl": "doktorant"}}}]},
        "4": {"id": "4", "last_name": "L4", "staff_status": 2, "phd_student_status": 2, "employment_positions": adjunct},
        "5": {"id": "5", "last_name": "L5", "staff_status": 2, "student_status": 2, "employment_positions": adjunct},
        "7": {"id": "7", "last_name": "L7", "staff_status": 2, "employment_positions": []},
        # wspolpracownik na umowie cywilnoprawnej (staff_status 1) - karta
        "8": {"id": "8", "last_name": "L8", "staff_status": 1, "employment_positions": [
            {"position": {"name": {"pl": "współpracownik"}}, "faculty": {"name": {"pl": "Umowy cywilnoprawne (ogólne)"}}}]},
        # nie pracuje na UJ
        "6": {"id": "6", "last_name": "L6", "staff_status": 0, "employment_positions": adjunct},
    }
    ctx = context({
        "services/courses/course": {**COURSE, "terms": [{"id": "26/27Z"}]},
        "services/courses/course_edition2": {},
        "services/tt/course_edition": _tt,
        "services/groups/groups": {"(11,1)": {"lecturers": group_lecturers}, "(12,2)": {"lecturers": []}},
        "services/users/users": users,
    }, active_terms=[TERM], course_editions={("WMI.IM-AM1", "26/27Z"): set()}, staff={})

    records = _valid(courses.collect(ctx))

    assert [(r.kind, r.id) for r in records] == [("course", "course:WMI.IM-AM1"), ("lecturer", "2"), ("lecturer", "8")]


def test_lecturers_of_skipped_courses_get_no_card():
    ctx = context({
        "services/courses/course": {**COURSE, "fac_id": "UJ.WCh", "terms": [{"id": "26/27Z"}]},
        "services/courses/course_edition2": {},
        "services/tt/course_edition": _tt,
        "services/groups/groups": {"(11,1)": {"lecturers": [{"id": "2", "last_name": "L2"}]}},
    }, active_terms=[TERM], course_editions={("WMI.IM-AM1", "26/27Z"): set()}, staff={})

    assert _valid(courses.collect(ctx)) == []
    assert "services/users/users" not in ctx.api.methods()
