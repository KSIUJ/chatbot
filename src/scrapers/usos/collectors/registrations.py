"""
Rejestracje na przedmioty i rejestracje zetonowe jednostek wydzialu (z kluczem
aplikacji): opis, tury (terminy, tryb, limit wyborow) i przedmioty do wyboru
w turach z limitami miejsc. Jeden rekord na rejestracje.

Rejestracje na przedmioty sa przypiete do instytutow (UJ.WMI.II, UJ.WMI.IM), nie
do wydzialu; zetonowe (zajecia ogolnouczelniane, WF) - do UJ i UJ.SWF. Brane
sa wszystkie (active_only=false), ale tylko tury zakonczone najwyzej
FINISHED_DAYS temu, wiec zostaje biezacy i poprzedni semestr.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

from src.backend.rag.sources.usos.dataset import RegistrationAttributes, RegistrationRecord

from ..api import UsosError, fields
from .units import is_technical
from ..context import Context
from ..text import document, format_date, format_period, parse_datetime, pick, pick_markdown, section, table

NAME = "registrations"
NEEDS_CONSUMER = True

FINISHED_DAYS = 180
REGISTRATION_FIELDS = fields("id", "description", "message", "type", "status", "faculty", "www_instance", "rounds")
TOKEN_FIELDS = fields("id", "description", "short_description", "message", "status", "faculty", "rounds")
ROUND_FIELDS = fields(
    "id", "name", "status", "registration_mode", "start_date", "end_date", "selection_limit", "is_dedicated",
)
TOKEN_ROUND_FIELDS = fields("id", "name", "start_date", "end_date", "selection_limit", "is_dedicated")
# bez liczby zapisanych - zmienia sie co chwile, a nieaktualna wprowadza w blad
ROUND_COURSE_FIELDS = fields("course", "term_id", "status", "limits")
MODES = {
    "double_for_courses": "dwuetapowa na przedmioty (zapis na listę, potem rozstrzygnięcie)",
    "double_for_group_with_ask": "dwuetapowa do grup (prośba o przyjęcie)",
    "double_group_manual": "dwuetapowa do grup (bez akceptacji)",
    "direct_for__courses_and_groups": "bezpośrednia do przedmiotów i grup (kto pierwszy)",
}
ROUND_STATUSES = {"active": "trwa", "preparing": "w przygotowaniu", "closed": "zamknięta"}
REGISTRATION_STATUSES = {"active": "aktywna", "finished": "zakończona", "inactive": "nieaktywna"}
# rejestracje zetonowe dla calej uczelni: zajecia ogolnouczelniane, Artes Liberales, WF
UNIVERSITY_UNITS = ("UJ", "UJ.SWF")


def _rounds(ctx: Context, registration: dict, token: bool) -> list[dict]:
    rounds = [r for r in registration.get("rounds") or [] if isinstance(r, dict)]
    method = "services/registrations/token_registration_round" if token else "services/registrations/registration_round"
    full = []
    for item in rounds:
        # rounds bywa lista samych id - wtedy dociagamy szczegoly tury
        if "start_date" not in item and item.get("id") is not None:
            item = ctx.api.call(method, id=item["id"], fields=TOKEN_ROUND_FIELDS if token else ROUND_FIELDS)
        full.append(item)
    return full


def _recent(round_: dict, today: date) -> bool:
    end = parse_datetime(round_.get("end_date"))
    return end is None or end.date() >= today - timedelta(days=FINISHED_DAYS)


def _round_courses(ctx: Context, round_id: str) -> dict[str, dict]:
    """Przedmioty tury: kod -> {name, term, limit}."""
    got = ctx.api.call(
        "services/registrations/registration_round_courses", registration_round_id=round_id, fields=ROUND_COURSE_FIELDS
    )
    courses = {}
    for entry in got or []:
        course = entry.get("course") or {}
        if not course.get("id"):
            continue
        limits = entry.get("limits")
        limit = limits.get("total") if isinstance(limits, dict) else limits
        courses[str(course["id"])] = {
            "name": pick(course.get("name")),
            "term": str(entry.get("term_id") or ""),
            # brak albo 0 - bez limitu
            "limit": "" if limit in (None, "", 0) else str(limit),
        }
    return courses


def _courses_table(per_round: list[tuple[int, dict[str, dict]]]) -> str:
    """Jedna tabela przedmiotow rejestracji; tury czesto maja te same przedmioty
    (np. kolejne progi sredniej) - kolumna "tury" tylko, gdy sie roznia."""
    all_courses: dict[str, dict] = {}
    rounds_of: dict[str, list[int]] = {}
    for number, courses in per_round:
        for code, course in courses.items():
            all_courses.setdefault(code, dict(course))
            rounds_of.setdefault(code, []).append(number)
    same = len({tuple(sorted(c)) for _n, c in per_round}) <= 1
    header = ["przedmiot", "kod", "cykl", "limit miejsc"] + ([] if same else ["tury"])
    rows = []
    for code, course in sorted(all_courses.items(), key=lambda item: (item[1]["name"], item[0])):
        row = [course["name"], code, course["term"], course["limit"]]
        rows.append(row if same else row + [", ".join(str(n) for n in rounds_of[code])])
    return table(header, rows)


def registration_record(ctx: Context, registration: dict, token: bool) -> RegistrationRecord | None:
    registration_id = str(registration.get("id") or "")
    if not registration_id:
        return None
    rounds = [r for r in _rounds(ctx, registration, token) if _recent(r, ctx.today)]
    if not rounds:
        return None
    description = pick(registration.get("description")) or f"Rejestracja {registration_id}"
    faculty = registration.get("faculty") or {}
    fac_id = str(faculty.get("id") or "")
    unit = pick(faculty.get("name")) or ctx.unit_names.get(fac_id, fac_id)
    kind = "żetonowa" if token else "na przedmioty"

    round_rows: list[list[str]] = []
    per_round: list[tuple[int, dict[str, dict]]] = []
    starts, ends = [], []
    for number, round_ in enumerate(sorted(rounds, key=lambda r: r.get("start_date") or ""), start=1):
        start, end = parse_datetime(round_.get("start_date")), parse_datetime(round_.get("end_date"))
        starts += [start] if start else []
        ends += [end] if end else []
        name = pick(round_.get("name")) or f"Tura {round_.get('id')}"
        round_rows.append([
            str(number), name, format_period(start, end), MODES.get(round_.get("registration_mode") or "", round_.get("registration_mode") or ""),
            ROUND_STATUSES.get(round_.get("status") or "", round_.get("status") or ""),
            "" if round_.get("selection_limit") in (None, 0) else str(round_["selection_limit"]),
        ])
        if not token and round_.get("id") is not None:
            try:
                per_round.append((number, _round_courses(ctx, str(round_["id"]))))
            except UsosError as error:
                ctx.warn(f"{NAME}: przedmioty tury {round_['id']} niedostepne ({error})")

    message = pick_markdown(registration.get("message"), heading_offset=2)
    info = "\n".join(line for line in (
        f"- Rodzaj: rejestracja {kind}",
        f"- Jednostka: {unit}" if unit else "",
        f"- Kod rejestracji: {registration_id}",
        f"- Status: {REGISTRATION_STATUSES.get(registration.get('status') or '', registration.get('status') or '')}"
        if registration.get("status") else "",
    ) if line)
    return RegistrationRecord(
        id=f"registration:{'token:' if token else ''}{registration_id}",
        kind="registration",
        title=description,
        # kalendarz rejestracji jednostki (zetonowe: jedna strona) - z kotwica, zeby kazdy
        # rekord mial wlasny adres
        url=(
            ctx.usosweb("news/rejestracjeZetonowe") if token
            else ctx.usosweb("news/rejestracje/rejJednostki", jed_org_kod=fac_id or ctx.faculty)
        ) + f"#{registration_id}",
        lang="pl",
        content=document(
            f"# {description}",
            section("Informacje", info),
            section("Komunikat", message),
            section("Tury rejestracji", table(["nr", "tura", "termin", "tryb", "status", "limit wyborów"], round_rows)),
            section("Przedmioty do wyboru", _courses_table(per_round)),
        ),
        attributes=RegistrationAttributes(
            registration_id=registration_id,
            fac_id=fac_id,
            registration_type="token" if token else "course",
            start_date=min(starts).date() if starts else None,
            end_date=max(ends).date() if ends else None,
        ),
    )


def collect(ctx: Context) -> Iterator[RegistrationRecord]:
    units = list(dict.fromkeys([*(ctx.faculty_units or [ctx.faculty]), *UNIVERSITY_UNITS]))
    for faculty in units:
        if is_technical(faculty):
            continue
        for token, method, fields_ in (
            (False, "services/registrations/faculty_registrations", REGISTRATION_FIELDS),
            (True, "services/registrations/faculty_token_registrations", TOKEN_FIELDS),
        ):
            try:
                found = ctx.api.call(method, faculty_id=faculty, active_only=False, fields=fields_) or []
            except UsosError as error:
                ctx.warn(f"{NAME}: rejestracje jednostki {faculty} niedostepne ({error})")
                continue
            for registration in found:
                if not isinstance(registration, dict):
                    continue
                try:
                    record = registration_record(ctx, registration, token)
                except UsosError as error:
                    ctx.warn(f"{NAME}: rejestracja {registration.get('id')} pominieta ({error})")
                    continue
                if record is not None:
                    yield record
