"""
Programy studiow wydzialu (progs/search + progs/programmes - bez klucza).

USOS API nie ma listy programow jednostki, a progs/search zwraca najwyzej
100 wynikow na zapytanie (num <= 20, stronicowane). Wyszukiwanie dopasowuje
slowa do kodu i nazwy programu (kilka slow = wszystkie naraz), wiec:
- "WMI" znajduje programy z kodem WMI-..., D_WMI_..., MOST-WMI... itp.,
- "MSMP" - programy wydzialu w ramach Miedzywydzialowych Studiow
  Matematyczno-Przyrodniczych (kody MSMP-..., bez "WMI"),
- slowa kluczowe kierunkow - zabezpieczenie na programy o innych kodach.
Wyniki sa laczone, a zostaja tylko te, ktorych jednostka prowadzaca
(faculty) nalezy do wydzialu. Gdy zapytanie dobije do limitu 100, jest
powtarzane z dodatkowymi slowami (REFINEMENTS), a gdy i to nie wystarcza -
ostrzezenie.

Pomijane sa pseudo-programy wymiany (Erasmus, MOST, CEEPUS, studenci z
Ukrainy - "krotkoterminowe"). Kolejne edycje studiow podyplomowych i kursow
(kody rozniace sie litera edycji: WMI-525A-P, WMI-525B-P, ...; ta sama nazwa)
sa laczone w jeden rekord z lista kodow - inaczej kilkadziesiat identycznych
rekordow zagluszaloby wyszukiwanie. Rozne programy o tej samej nazwie (stary
i nowy kod kierunku) zostaja osobno, z kodem w tytule.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator

from src.backend.rag.sources.usos.dataset import ProgrammeAttributes, ProgrammeRecord

from ..api import fields
from ..context import Context
from ..text import document, pick, pick_text, section

NAME = "programmes"
NEEDS_CONSUMER = False

QUERIES = ("WMI", "MSMP", "informatyka", "matematyka", "Computer", "Mathematics")
# dodatkowe slowa dla zapytan obcietych do SEARCH_LIMIT wynikow
REFINEMENTS = ("stopnia", "podyplomowe", "kurs", "doktoranckie", "stacjonarne", "niestacjonarne")
SEARCH_LIMIT = 100
SEARCH_PAGE = 20
SEARCH_FIELDS = "items[programme[id|faculty[id]]]|next_page"
PROGRAMME_FIELDS = fields(
    "id", "name", "description", "faculty[id|name]", "all_faculties[id|name]", "mode_of_studies",
    "level_of_studies", "duration", "professional_status", "level",
)
# pseudo-programy wymiany studenckiej (nie sa kierunkami studiow)
EXCHANGE_PREFIXES = ("ER-", "MOST-", "CEEPUS-", "UA-")
EXCHANGE_LEVELS = {"krótkoterminowe"}
# kod edycji studiow podyplomowych / kursu: WMI-525A-P, WMI-701AB-K
EDITION_ID = re.compile(r"^(?P<base>[A-Za-z_]+-\d+)[A-Z]{1,2}-(?P<kind>[A-Z])$")
LEVEL_ORDER = {"first_cycle": 0, "second_cycle": 1, "long_cycle": 2, "third_cycle": 3, "phd_school": 4}


def _search(ctx: Context, query: str) -> list[dict]:
    items = ctx.api.pages(
        "services/progs/search", num=SEARCH_PAGE, limit=SEARCH_LIMIT, lang=ctx.lang, query=query, fields=SEARCH_FIELDS
    )
    return [item["programme"] for item in items if isinstance(item, dict) and isinstance(item.get("programme"), dict)]


def search_ids(ctx: Context) -> set[str]:
    """Id programow, ktorych jednostka prowadzaca nalezy do wydzialu."""
    found: dict[str, dict] = {}
    pending = list(QUERIES)
    seen: set[str] = set()
    while pending:
        query = pending.pop(0)
        if query in seen:
            continue
        seen.add(query)
        got = _search(ctx, query)
        found.update({str(p["id"]): p for p in got if p.get("id")})
        if len(got) >= SEARCH_LIMIT:
            if " " in query:
                ctx.warn(
                    f"{NAME}: zapytanie {query!r} obciete do {SEARCH_LIMIT} wynikow - czesc programow moze brakowac"
                )
            else:
                pending += [f"{query} {word}" for word in REFINEMENTS]
    return {pid for pid, p in found.items() if in_faculty(ctx, (p.get("faculty") or {}).get("id"))}


def in_faculty(ctx: Context, fac_id: object) -> bool:
    return ctx.in_faculty(fac_id)


def is_exchange(programme: dict) -> bool:
    pid = str(programme.get("id") or "")
    return pid.startswith(EXCHANGE_PREFIXES) or pick(programme.get("level_of_studies"), "pl") in EXCHANGE_LEVELS


def _base_name(programme: dict) -> str:
    """Nazwa bez dopisku rodzaju studiow ("..., podyplomowe", "..., kurs")."""
    name = pick(programme.get("name"), "pl")
    level = pick(programme.get("level_of_studies"), "pl")
    if level and name.casefold().endswith(", " + level.casefold()):
        name = name[: -len(level) - 2]
    return name.strip()


def group_key(programme: dict) -> tuple[str, ...]:
    """Edycje jednego programu (WMI-525A-P, WMI-525B-P) maja wspolny klucz:
    kod bez litery edycji i nazwa; pozostale programy - wlasny kod."""
    pid = str(programme.get("id") or "")
    match = EDITION_ID.match(pid)
    if not match:
        return (pid,)
    return (match["base"] + "-" + match["kind"], _base_name(programme).casefold())


def programme_record(ctx: Context, group: list[dict]) -> ProgrammeRecord | None:
    group = sorted(group, key=lambda p: str(p["id"]))
    first = group[0]
    pid = str(first["id"])
    names = Counter(pick(p.get("name"), "pl") for p in group if pick(p.get("name"), "pl"))
    if not names:
        return None
    # najczestszy wariant nazwy (edycje roznia sie czasem wielkoscia liter)
    title = max(names, key=lambda n: (names[n], n == pick(first.get("name"), "pl")))
    ids = [str(p["id"]) for p in group]
    level = pick(first.get("level_of_studies"), "pl")
    mode = pick(first.get("mode_of_studies"), "pl")
    durations = list(dict.fromkeys(pick(p.get("duration"), "pl") for p in group if pick(p.get("duration"), "pl")))
    status = list(dict.fromkeys(
        pick_text(p.get("professional_status"), "pl") for p in group if pick_text(p.get("professional_status"), "pl")
    ))
    faculty = first.get("faculty") or {}
    faculty_id = str(faculty.get("id") or "")
    faculty_name = pick(faculty.get("name"), "pl") or ctx.unit_names.get(faculty_id, "")
    english = pick((first.get("name") or {}).get("en")) if isinstance(first.get("name"), dict) else ""
    # description w USOS API to dzis alias nazwy - dodawany tylko, gdy jest czyms wiecej
    description = pick_text(first.get("description"), "pl")
    related = list(dict.fromkeys(
        pick(f.get("name"), "pl") or ctx.unit_names.get(str(f.get("id")), "")
        for f in first.get("all_faculties") or []
        if isinstance(f, dict) and str(f.get("id") or "") != faculty_id
    ))

    info = [
        f"- Poziom studiów: {level}" if level else "",
        f"- Tryb studiów: {mode}" if mode else "",
        f"- Czas trwania: {', '.join(durations)}" if durations else "",
        f"- Kwalifikacje absolwenta: {'; '.join(status)}" if status else "",
        f"- Jednostka prowadząca: {faculty_name}" if faculty_name else "",
        f"- Inne jednostki związane z programem: {', '.join(r for r in related if r)}" if any(related) else "",
        f"- Nazwa angielska: {english}" if english and english != title else "",
    ]
    codes = (
        f"Kod programu w USOS: {pid}."
        if len(ids) == 1
        else f"Program ma w USOS kilka kodów (kolejne edycje): {', '.join(ids)}."
    )
    about = description if description and description not in (title, _base_name(first)) else ""
    content = document(
        f"# {title}",
        f"Program studiów na Uniwersytecie Jagiellońskim: {title}. {codes}",
        section("Informacje o programie", "\n".join(line for line in info if line)),
        section("Opis", about),
    )
    return ProgrammeRecord(
        id=f"programme:{pid}",
        kind="programme",
        title=title,
        url=ctx.usosweb("katalog2/programy/pokazProgram", kod=pid),
        lang="pl",
        content=content,
        attributes=ProgrammeAttributes(
            programme_id=pid, fac_id=faculty_id, level=level, mode=mode, duration=", ".join(durations)
        ),
    )


def collect(ctx: Context) -> Iterator[ProgrammeRecord]:
    ids = sorted(search_ids(ctx))
    programmes = ctx.api.batch("services/progs/programmes", "programme_ids", ids, fields=PROGRAMME_FIELDS)
    groups: dict[tuple[str, ...], list[dict]] = {}
    for pid in ids:
        programme = programmes.get(pid)
        if not isinstance(programme, dict) or not programme.get("id"):
            continue
        if is_exchange(programme) or not in_faculty(ctx, (programme.get("faculty") or {}).get("id")):
            continue
        groups.setdefault(group_key(programme), []).append(programme)

    def order(group: list[dict]) -> tuple:
        first = min(group, key=lambda p: str(p["id"]))
        return (LEVEL_ORDER.get(first.get("level"), 9), _base_name(first).casefold(), str(first["id"]))

    records = [r for r in (programme_record(ctx, group) for group in sorted(groups.values(), key=order)) if r]
    # rozne programy o tej samej nazwie (np. stary i nowy kod kierunku) - tytul z kodem
    titles = Counter(r.title for r in records)
    for record in records:
        if titles[record.title] > 1:
            record = record.model_copy(update={"title": f"{record.title} ({record.attributes.programme_id})"})
        yield record
