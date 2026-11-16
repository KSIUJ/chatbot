"""
Budynki i domy studenckie UJ (geo/*, housing/* - bez klucza).

Budynki: lista wszystkich (geo/building_index), dane z geo/buildings2
(nazwa, kampus, adres, telefony, jednostki w budynku). Budynki wydzialu
(jednostka z ctx.faculty_units wsrod related_faculties) i budynki z zajeciami
wydzialu (ctx.teaching_buildings, kolektor courses) dostaja tez sale
(geo/rooms: numer, liczba miejsc, rodzaj i wyposazenie); pokoje pracownikow
tylko jako lista numerow i tylko w budynkach wydzialu - bez osob
przypisanych do pokoi.

Domy studenckie: bez tokenu uzytkownika USOS API podaje tylko nazwe i skrot
(pokoje akademika wymagaja tokenu), wiec zamiast kilkunastu prawie pustych
rekordow powstaje jeden przeglad "Domy studenckie UJ" (dormitory:all).
"""

from __future__ import annotations

from collections.abc import Iterator

from src.backend.rag.sources.usos.dataset import (
    BuildingAttributes,
    BuildingRecord,
    DormitoryAttributes,
    DormitoryRecord,
)

from ..api import UsosError, fields
from ..context import Context
from ..text import document, pick, section, table
from .units import phones

NAME = "places"
NEEDS_CONSUMER = False

BUILDING_FIELDS = fields(
    "id", "name", "profile_url", "postal_address", "campus_name", "phone_numbers", "all_phone_numbers",
    "related_faculties[id|name]",
)
INDEX_FIELDS = fields("id")
BUILDING_ROOMS_FIELDS = fields("id", "rooms[id]")
ROOM_FIELDS = fields("id", "number", "type", "capacity", "attributes")
DORMITORY_FIELDS = fields("id", "name", "short_name")
DIDACTIC_TYPES = {"didactics_room", "D"}
STAFF_TYPES = {"staff_members_room", "P"}
# atrybuty sal, ktore opisuja rodzaj sali, a nie wyposazenie
KIND_PREFIXES = ("SALA-", "LABORATORIUM")
# powyzej tylu sal tabela jest dzielona na podsekcje wedlug pierwszej cyfry numeru
SPLIT_ROOMS = 25


def related_faculties(building: dict) -> list[dict]:
    return [f for f in building.get("related_faculties") or [] if isinstance(f, dict) and f.get("id")]


def _room_sort(room: dict) -> tuple:
    number = pick(room.get("number"))
    return (not number[:1].isdigit(), number)


def _room_row(room: dict) -> list[str]:
    kinds: list[str] = []
    equipment: list[str] = []
    for attribute in room.get("attributes") or []:
        if not isinstance(attribute, dict):
            continue
        text = pick(attribute.get("description"), "pl")
        if not text:
            continue
        count = attribute.get("count")
        if isinstance(count, int) and count > 1:
            text = f"{text} ({count})"
        (kinds if str(attribute.get("id") or "").startswith(KIND_PREFIXES) else equipment).append(text)
    capacity = room.get("capacity")
    return [
        pick(room.get("number")),
        str(capacity) if isinstance(capacity, int) and capacity > 0 else "",
        ", ".join(dict.fromkeys(kinds)),
        ", ".join(dict.fromkeys(equipment)),
    ]


def rooms_markdown(rooms: list[dict], with_staff_rooms: bool) -> str:
    didactic = sorted((r for r in rooms if r.get("type") in DIDACTIC_TYPES and pick(r.get("number"))), key=_room_sort)
    header = ("Sala", "Miejsca", "Rodzaj", "Wyposażenie")
    parts: list[str] = []
    if len(didactic) > SPLIT_ROOMS:
        # sale wedlug pierwszej cyfry numeru - mniejsze tabele dziela sie na fragmenty z naglowkiem
        groups: dict[str, list[dict]] = {}
        for room in didactic:
            number = pick(room.get("number"))
            key = f"Sale {number[0]}xxx" if len(number) >= 4 and number[0].isdigit() else "Pozostałe sale"
            groups.setdefault(key, []).append(room)
        body = "\n\n".join(
            section(key, table(header, [_room_row(r) for r in group]), level=3) for key, group in groups.items()
        )
        parts.append(section("Sale dydaktyczne", body))
    else:
        parts.append(section("Sale dydaktyczne", table(header, [_room_row(r) for r in didactic])))
    if with_staff_rooms:
        offices = sorted(
            {pick(r.get("number")) for r in rooms if r.get("type") in STAFF_TYPES and pick(r.get("number"))} - {"nn"},
            key=lambda n: (not n[:1].isdigit(), n),
        )
        parts.append(section("Pokoje pracowników", ", ".join(offices)))
    return "\n\n".join(p for p in parts if p)


def building_record(
    ctx: Context, building: dict, rooms: list[dict] | None, faculty_building: bool
) -> BuildingRecord | None:
    building_id = str(building.get("id") or "")
    name = pick(building.get("name"), "pl")
    if not building_id or not name:
        return None
    campus = pick(building.get("campus_name"), "pl")
    address = pick(building.get("postal_address"))
    building_phones = phones(building)
    faculties = related_faculties(building)
    info = [
        f"- Kampus: {campus}" if campus else "",
        f"- Adres: {address}" if address else "",
        f"- Telefon: {', '.join(building_phones)}" if building_phones else "",
        f"- Kod budynku w USOS: {building_id}",
    ]
    units = list(dict.fromkeys(pick(f.get("name"), "pl") for f in faculties if pick(f.get("name"), "pl")))
    content = document(
        f"# {name}",
        "Budynek Uniwersytetu Jagiellońskiego." + (f" Adres: {address}." if address else ""),
        section("Informacje", "\n".join(line for line in info if line)),
        section("Jednostki w budynku", "\n".join(f"- {u}" for u in units)),
        rooms_markdown(rooms, with_staff_rooms=faculty_building) if rooms else "",
    )
    url = pick(building.get("profile_url")) or ctx.usosweb("katalog2/jednostki/pokazBudynek", bud_kod=building_id)
    return BuildingRecord(
        id=f"building:{building_id}",
        kind="building",
        title=name,
        url=url,
        lang="pl",
        content=content,
        attributes=BuildingAttributes(
            building_id=building_id, campus=campus, address=address, fac_ids=[str(f["id"]) for f in faculties]
        ),
    )


def _rooms(ctx: Context, building_ids: list[str]) -> dict[str, list[dict]]:
    """Sale budynkow: id sal z geo/buildings2, szczegoly z geo/rooms (bez
    klucza; blad API - budynki bez sal zamiast przerwania kolektora)."""
    if not building_ids:
        return {}
    try:
        with_rooms = ctx.api.batch("services/geo/buildings2", "building_ids", building_ids, fields=BUILDING_ROOMS_FIELDS)
        room_ids = {
            str(room["id"]): building_id
            for building_id, building in with_rooms.items()
            for room in building.get("rooms") or []
            if isinstance(room, dict) and room.get("id")
        }
        details = ctx.api.batch("services/geo/rooms", "room_ids", list(room_ids), fields=ROOM_FIELDS)
    except UsosError as error:
        ctx.warn(f"{NAME}: sale niepobrane, budynki bez listy sal - {error}")
        return {}
    out: dict[str, list[dict]] = {}
    for room_id, building_id in room_ids.items():
        if isinstance(details.get(room_id), dict):
            out.setdefault(building_id, []).append(details[room_id])
    return out


def buildings(ctx: Context) -> Iterator[BuildingRecord]:
    index = ctx.api.call("services/geo/building_index", fields=INDEX_FIELDS) or []
    ids = list(dict.fromkeys(str(b["id"]) for b in index if isinstance(b, dict) and b.get("id")))
    data = ctx.api.batch("services/geo/buildings2", "building_ids", ids, langpref="pl", fields=BUILDING_FIELDS)
    units = set(ctx.faculty_units) | {ctx.faculty}
    faculty_ids = [i for i in ids if i in data and any(str(f["id"]) in units for f in related_faculties(data[i]))]
    teaching = [i for i in ids if i in data and i in ctx.teaching_buildings and i not in faculty_ids]
    unknown = sorted(set(ctx.teaching_buildings) - set(data))
    if unknown:
        ctx.warn(f"{NAME}: budynki z planu zajec spoza geo/building_index: {', '.join(unknown)}")
    rooms = _rooms(ctx, faculty_ids + teaching)
    for building_id in ids:
        if building_id not in data:
            continue
        record = building_record(ctx, data[building_id], rooms.get(building_id), building_id in faculty_ids)
        if record:
            yield record


def dormitories_record(ctx: Context) -> DormitoryRecord | None:
    try:
        index = ctx.api.call("services/housing/dormitory_index", fields=DORMITORY_FIELDS) or []
    except UsosError as error:
        ctx.warn(f"{NAME}: domy studenckie niepobrane - {error}")
        return None
    rows = []
    for dorm in index:
        if not isinstance(dorm, dict):
            continue
        name = pick(dorm.get("name"), "pl")
        if name:
            short = pick(dorm.get("short_name"), "pl")
            rows.append((name, short if short and short != name else ""))
    if not rows:
        return None
    rows.sort(key=lambda row: row[0].casefold())
    content = document(
        "# Domy studenckie UJ",
        "Domy studenckie (akademiki) Uniwersytetu Jagiellońskiego zapisane w systemie USOS "
        "– nazwy i skróty, którymi USOS oznacza akademiki (np. przy przydziale miejsc).",
        section("Lista domów studenckich", table(("Dom studencki", "Skrót w USOS"), rows)),
    )
    return DormitoryRecord(
        id="dormitory:all",
        kind="dormitory",
        title="Domy studenckie UJ",
        lang="pl",
        content=content,
        attributes=DormitoryAttributes(dormitory_id="all"),
    )


def collect(ctx: Context) -> Iterator[BuildingRecord | DormitoryRecord]:
    yield from buildings(ctx)
    record = dormitories_record(ctx)
    if record:
        yield record
