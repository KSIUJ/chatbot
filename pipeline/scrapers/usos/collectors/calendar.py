"""
Kalendarz akademicki: aktywne cykle dydaktyczne (rok akademicki i semestry,
terms/terms_index - bez klucza) oraz wydarzenia kalendarza USOS - dni wolne,
przerwy, sesje (calendar/search - z kluczem, okna najwyzej miesieczne).

Jeden rekord na aktywny rok akademicki. Ustala ctx.active_terms (semestry
i rok), z ktorych korzystaja pozniejsze kolektory (przedmioty, rejestracje).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

from src.backend.rag.sources.usos.dataset import CalendarAttributes, CalendarRecord

from ..api import ConsumerRequired, UsosError, fields
from ..context import Context, Term
from ..text import document, format_date, format_period, parse_date, pick, section, table

NAME = "calendar"
NEEDS_CONSUMER = False

EVENT_TYPES = {
    "holidays": "święto",
    "break": "przerwa",
    "exam_session": "sesja egzaminacyjna",
}
# wpisy techniczne USOS (okna edycji linkow) - bez nazwy, nie dla studentow
SKIPPED_TYPES = {"links_edit"}
EVENT_FIELDS = fields("id", "name", "start_date", "end_date", "type", "is_day_off", "faculty")


def _terms(ctx: Context) -> list[dict]:
    got = ctx.api.call("services/terms/terms_index", active_only=True)
    return [t for t in got if isinstance(t, dict) and t.get("id")]


def _is_year(term: dict) -> bool:
    # rok akademicki "26/27", semestry "26/27Z" / "26/27L"
    return "/" in term["id"] and term["id"][-1].isdigit()


def _months(start: date, end: date) -> Iterator[tuple[date, date]]:
    """Okna najwyzej miesieczne (limit calendar/search)."""
    current = start
    while current <= end:
        stop = min(current + timedelta(days=30), end)
        yield current, stop
        current = stop + timedelta(days=1)


def _events(ctx: Context, start: date, end: date) -> list[dict]:
    seen: dict[str, dict] = {}
    # zapytanie o wydzial zwraca tez wydarzenia calej uczelni (faculty "UJ")
    for window_start, window_end in _months(start, end):
        got = ctx.api.call(
            "services/calendar/search",
            faculty_id=ctx.faculty,
            start_date=window_start.isoformat(),
            end_date=window_end.isoformat(),
            fields=EVENT_FIELDS,
        )
        for event in got or []:
            if not isinstance(event, dict) or event.get("id") is None:
                continue
            if event.get("type") in SKIPPED_TYPES or not pick(event.get("name")):
                continue
            seen.setdefault(str(event["id"]), event)
    return sorted(seen.values(), key=lambda e: (e.get("start_date") or "", e.get("end_date") or ""))


def _event_row(event: dict) -> list[str]:
    start, end = parse_date(event.get("start_date")), parse_date(event.get("end_date"))
    period = format_date(start) if start and start == end else format_period(start, end)
    kind = EVENT_TYPES.get(event.get("type") or "", event.get("type") or "")
    faculty = pick((event.get("faculty") or {}).get("name"))
    return [pick(event.get("name")), period, kind, "tak" if event.get("is_day_off") else "", faculty]


def collect(ctx: Context) -> Iterator[CalendarRecord]:
    terms = _terms(ctx)
    years = [t for t in terms if _is_year(t)]
    semesters = [t for t in terms if not _is_year(t)]
    ctx.active_terms = [
        Term(t["id"], pick(t.get("name")), parse_date(t.get("start_date")), parse_date(t.get("end_date")))
        for t in terms
        if parse_date(t.get("start_date")) and parse_date(t.get("end_date"))
    ]

    for year in years:
        start, end = parse_date(year.get("start_date")), parse_date(year.get("end_date"))
        finish = parse_date(year.get("finish_date"))
        if start is None or end is None:
            ctx.warn(f"{NAME}: cykl {year['id']} bez dat - pomijam")
            continue
        year_semesters = [s for s in semesters if s["id"].startswith(year["id"])]
        rows = [
            [pick(s.get("name")), s["id"], format_date(parse_date(s.get("start_date"))),
             format_date(parse_date(s.get("end_date"))), format_date(parse_date(s.get("finish_date")))]
            for s in sorted(year_semesters, key=lambda s: s.get("order_key") or 0)
        ]
        cycles = table(["cykl", "kod", "początek", "koniec", "termin rozliczenia"], rows)

        events_md = ""
        try:
            # caly rok z wakacjami - do terminu rozliczenia cyklu
            events = _events(ctx, start, max(end, finish or end))
            events_md = table(["wydarzenie", "termin", "rodzaj", "bez zajęć", "jednostka"], map(_event_row, events))
        except ConsumerRequired:
            ctx.warn(f"{NAME}: wydarzenia kalendarza wymagaja klucza aplikacji - sa tylko cykle")
        except UsosError as error:
            ctx.warn(f"{NAME}: wydarzenia kalendarza niedostepne ({error})")

        name = pick(year.get("name")) or f"Rok akademicki {year['id']}"
        # "Rok akademicki 2026/2027" -> "Kalendarz akademicki 2026/2027 (26/27)"
        title = f"Kalendarz akademicki {name.removeprefix('Rok akademicki').strip() or year['id']} ({year['id']})"
        yield CalendarRecord(
            id=f"calendar:{year['id']}:{ctx.faculty}",
            kind="calendar",
            title=title,
            lang="pl",
            content=document(
                f"# {title}",
                f"{name}: {format_period(start, end)}"
                + (f", termin rozliczenia cyklu {format_date(finish)}" if finish else "")
                + ". Daty z USOS (cykle dydaktyczne UJ).",
                section("Semestry", cycles),
                section("Wydarzenia, przerwy i dni wolne", events_md),
            ),
            attributes=CalendarAttributes(
                academic_year=year["id"], fac_id=ctx.faculty, start_date=start, end_date=end,
            ),
        )
