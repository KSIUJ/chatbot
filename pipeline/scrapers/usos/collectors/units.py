"""
Jednostki organizacyjne wydzialu (fac/faculty, fac/subfaculties_deep,
fac/faculties - bez klucza): wydzial i wszystkie jego podjednostki (instytuty,
katedry, zaklady, biblioteki, dziekanat) z adresem, telefonami, strona,
jednostka nadrzedna i podrzednymi.

Jeden rekord na jednostke; jednostki techniczne USOS (umowy cywilno-prawne
"*.UCP", jednostki pomocnicze doktorantow "*.DOKT") nie maja rekordow, ale
trafiaja do ctx.faculty_units i ctx.unit_names - inne kolektory filtruja
i nazywaja po nich przedmioty i programy.
"""

from __future__ import annotations

from collections.abc import Iterator

from src.backend.rag.sources.usos.dataset import UnitAttributes, UnitRecord

from ..api import fields
from ..context import Context
from ..text import document, pick, section

NAME = "units"
NEEDS_CONSUMER = False

UNIT_FIELDS = fields(
    "id", "name", "profile_url", "homepage_url", "phone_numbers", "phone_numbers2", "postal_address", "email",
    "is_public", "path[id|name]",
)
# ostatni czlon id jednostek technicznych (bez rekordu)
TECHNICAL_SUFFIXES = {"UCP", "DOKT"}


def is_technical(fac_id: str) -> bool:
    """Jednostka techniczna USOS ("*.UCP", "*.DOKT") - bez wlasnego rekordu;
    inne kolektory (np. registrations) tez je pomijaja."""
    return fac_id.rsplit(".", 1)[-1] in TECHNICAL_SUFFIXES


def phones(item: dict) -> list[str]:
    """Telefony jednostki albo budynku: numery z komentarzem (phone_numbers2
    jednostek, all_phone_numbers budynkow), a gdy ich brak - phone_numbers."""
    out: list[str] = []
    for phone in [*(item.get("phone_numbers2") or []), *(item.get("all_phone_numbers") or [])]:
        if not isinstance(phone, dict):
            continue
        number = pick(phone.get("number"))
        comment = pick(phone.get("comment"), "pl")
        if number:
            out.append(f"{number} ({comment})" if comment else number)
    if not out:
        out = [pick(p) for p in item.get("phone_numbers") or [] if pick(p)]
    return list(dict.fromkeys(out))


def parent_of(unit: dict) -> dict:
    path = [p for p in unit.get("path") or [] if isinstance(p, dict) and p.get("id")]
    return path[-1] if path else {}


def unit_record(ctx: Context, unit: dict, children: list[dict]) -> UnitRecord | None:
    fac_id = str(unit.get("id") or "")
    name = pick(unit.get("name"), "pl")
    if not fac_id or not name:
        return None
    names = unit.get("name")
    english = pick(names.get("en")) if isinstance(names, dict) else ""
    parent = parent_of(unit)
    parent_name = pick(parent.get("name"), "pl")
    faculty_name = ctx.unit_names.get(ctx.faculty, "")

    intro = ["Jednostka organizacyjna Uniwersytetu Jagiellońskiego."]
    if fac_id != ctx.faculty and faculty_name:
        intro = [f"Jednostka organizacyjna Uniwersytetu Jagiellońskiego, część jednostki: {faculty_name}."]
    if english and english != name:
        intro.append(f"Nazwa angielska: {english}.")
    intro.append(f"Kod jednostki w USOS: {fac_id}.")

    unit_phones = phones(unit)
    contact = [
        f"- Adres: {pick(unit.get('postal_address'))}" if pick(unit.get("postal_address")) else "",
        f"- Telefon: {', '.join(unit_phones)}" if unit_phones else "",
        f"- E-mail: {pick(unit.get('email'))}" if pick(unit.get("email")) else "",
        f"- Strona internetowa: {pick(unit.get('homepage_url'))}" if pick(unit.get("homepage_url")) else "",
        f"- Strona w USOSweb: {pick(unit.get('profile_url'))}" if pick(unit.get("profile_url")) else "",
    ]
    structure = [f"- Jednostka nadrzędna: {parent_name}" if parent_name else ""]
    child_lines = [f"- {pick(c.get('name'), 'pl')} ({c['id']})" for c in children if pick(c.get("name"), "pl")]

    content = document(
        f"# {name}",
        "\n".join(intro),
        section("Kontakt", "\n".join(line for line in contact if line)),
        section("Struktura", "\n".join(line for line in structure if line)),
        section("Jednostki podrzędne", "\n".join(child_lines)),
    )
    url = pick(unit.get("profile_url")) or ctx.usosweb("katalog2/jednostki/pokazJednostke", kod=fac_id)
    return UnitRecord(
        id=f"unit:{fac_id}",
        kind="unit",
        title=name,
        url=url,
        lang="pl",
        content=content,
        attributes=UnitAttributes(fac_id=fac_id, parent_id=str(parent.get("id") or "")),
    )


def collect(ctx: Context) -> Iterator[UnitRecord]:
    faculty = ctx.api.call("services/fac/faculty", fac_id=ctx.faculty, fields=UNIT_FIELDS)
    sub_ids = [str(i) for i in ctx.api.call("services/fac/subfaculties_deep", fac_id=ctx.faculty) or []]
    sub_ids = [i for i in dict.fromkeys(sub_ids) if i != ctx.faculty]
    subunits = ctx.api.batch("services/fac/faculties", "fac_ids", sub_ids, fields=UNIT_FIELDS) if sub_ids else {}
    missing = [i for i in sub_ids if i not in subunits]
    if missing:
        ctx.warn(f"{NAME}: brak danych jednostek: {', '.join(missing)}")

    units = {ctx.faculty: faculty, **{i: subunits[i] for i in sub_ids if i in subunits}}
    ctx.faculty_units = list(dict.fromkeys([ctx.faculty, *sub_ids]))
    for fac_id, unit in units.items():
        name = pick((unit or {}).get("name"), "pl")
        if name:
            ctx.unit_names[fac_id] = name

    children: dict[str, list[dict]] = {}
    for fac_id, unit in units.items():
        if fac_id == ctx.faculty or is_technical(fac_id):
            continue
        parent_id = str(parent_of(unit).get("id") or "")
        children.setdefault(parent_id, []).append(unit)

    for fac_id, unit in units.items():
        if is_technical(fac_id):
            continue
        record = unit_record(ctx, unit, children.get(fac_id, []))
        if record:
            yield record
