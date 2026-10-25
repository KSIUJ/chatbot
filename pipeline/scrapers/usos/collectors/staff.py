"""
Pracownicy wydzialu (users/staff_index + users/users - z kluczem aplikacji):
karta pracownika (StaffRecord) - stanowiska, pokoj, dyzury, kontakt.

Zbierane sa tylko pola z publicznego profilu w USOSweb. Adres e-mail USOS
podaje tylko, gdy osoba go udostepnia (albo z tokenem uzytkownika
z uprawnieniem other_emails - USOS_ACCESS_TOKEN); bez niego pole zostaje puste.

Ustala ctx.staff (id -> imie i nazwisko z tytulami) i ctx.course_editions
(edycje przedmiotow prowadzone w aktywnych cyklach) dla kolektora przedmiotow.
"""

from __future__ import annotations

from collections.abc import Iterator

from src.backend.rag.sources.usos.dataset import Position, Room, StaffAttributes, StaffRecord

from ..api import fields
from ..context import Context
from ..text import pick, pick_text

NAME = "staff"
NEEDS_CONSUMER = True

USER_FIELDS = fields(
    "id", "first_name", "last_name", "titles", "staff_status", "email", "homepage_url", "profile_url",
    "phone_numbers", "office_hours", "interests", "room", "employment_positions", "course_editions_conducted",
)
# staff_status: 2 = obecny pracownik (1 = byly)
ACTIVE_STAFF = 2


def _staff_ids(ctx: Context) -> list[str]:
    units = ctx.faculty_units or [ctx.faculty]
    ids: dict[str, None] = {}
    for user in ctx.api.pages(
        "services/users/staff_index", items_key="users", fac_ids=units, fields="users[id]|next_page"
    ):
        if isinstance(user, dict) and user.get("id") is not None:
            ids[str(user["id"])] = None
    return list(ids)


def _room(raw: dict | None) -> Room | None:
    if not isinstance(raw, dict):
        return None
    number = str(raw.get("number") or "").strip()
    building = pick(raw.get("building_name"))
    return Room(number=number, building=building) if number or building else None


def _positions(raw: list | None) -> list[Position]:
    positions: list[Position] = []
    seen: set[tuple[str, str]] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = pick((item.get("position") or {}).get("name"))
        unit = pick((item.get("faculty") or {}).get("name"))
        if name and (name, unit) not in seen:
            seen.add((name, unit))
            positions.append(Position(name=name, unit=unit))
    return positions


def display_name(user: dict) -> str:
    titles = user.get("titles") or {}
    parts = [
        (titles.get("before") or "").strip(),
        " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p),
        (titles.get("after") or "").strip(),
    ]
    name = " ".join(p for p in parts[:2] if p)
    return f"{name}, {parts[2]}" if parts[2] else name


def staff_record(ctx: Context, user: dict) -> StaffRecord | None:
    user_id = str(user.get("id") or "")
    last_name = (user.get("last_name") or "").strip()
    if not user_id or not last_name:
        return None
    titles = user.get("titles") or {}
    first_name = (user.get("first_name") or "").strip()
    email = user.get("email")
    profile = user.get("profile_url") or ctx.usosweb("katalog2/osoby/pokazOsobe", os_id=user_id)
    return StaffRecord(
        id=user_id,
        kind="staff",
        title=" ".join(p for p in (first_name, last_name) if p),
        url=profile,
        lang="pl",
        attributes=StaffAttributes(
            usos_id=user_id,
            first_name=first_name,
            last_name=last_name,
            titles_before=(titles.get("before") or "").strip(),
            titles_after=(titles.get("after") or "").strip(),
            positions=_positions(user.get("employment_positions")),
            room=_room(user.get("room")),
            office_hours=pick_text(user.get("office_hours")),
            interests=pick_text(user.get("interests")),
            email=email.strip() if isinstance(email, str) else "",
            phones=[str(p).strip() for p in user.get("phone_numbers") or [] if str(p).strip()],
            homepage_url=(user.get("homepage_url") or "").strip(),
        ),
    )


def collect(ctx: Context) -> Iterator[StaffRecord]:
    if not ctx.active_terms:
        # bez cykli (kolektor calendar) edycje przedmiotow obejmowalyby cala historie
        raise RuntimeError("brak aktywnych cykli - kolektor calendar nie zadzialal")
    ids = _staff_ids(ctx)
    if not ids:
        raise RuntimeError(f"users/staff_index nie zwrocil pracownikow dla {ctx.faculty}")
    active_terms = {term.id for term in ctx.active_terms}
    # z tokenem (other_emails) USOS podaje tez adresy e-mail
    users = ctx.api.batch("services/users/users", "user_ids", ids, fields=USER_FIELDS, user=True)
    for user_id in ids:
        user = users.get(user_id)
        if not isinstance(user, dict):
            ctx.warn(f"{NAME}: brak danych osoby {user_id}")
            continue
        if user.get("staff_status") not in (None, ACTIVE_STAFF):
            continue
        record = staff_record(ctx, user)
        if record is None:
            ctx.warn(f"{NAME}: osoba {user_id} bez nazwiska - pomijam")
            continue
        ctx.staff[user_id] = display_name(user)
        for edition in user.get("course_editions_conducted") or []:
            course_id = (edition.get("course") or {}).get("id") or edition.get("course_id")
            term_id = (edition.get("term") or {}).get("id") or edition.get("term_id")
            if course_id and term_id and term_id in active_terms:
                ctx.course_editions.setdefault((str(course_id), str(term_id)), set()).add(user_id)
        yield record
