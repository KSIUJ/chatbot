"""
Konwersja danych z pipeline/scrapers/usos/scrape_staff.py do wspolnego schematu Document.

- Kazde uruchomienie scrapera zapisuje nowy plik
  data/usos/staff/staff_{fac_id}_{%Y%m%dT%H%M%SZ}.json; ingest bierze tylko
  najnowszy (sortowanie po nazwie), bez laczenia przebiegow.
- Jeden pracownik = jeden Document (rekordy sa krotkie, bez chunkowania).
- Ksztalt pol z normalize_employee(): `titles` to {"before", "after"},
  `room` to {"number", "building_name": {"pl", ...}} albo null,
  `employment_positions` to lista {"position": {"name": {"pl"}}, "faculty":
  {"name": {"pl"}}}; `office_hours_text` bywa HTML-em, wiec tagi sa usuwane.
"""

import glob
import json
import os
import re

from src.backend.rag.schema import Document, make_id

STAFF_DIR = os.path.join("data", "usos", "staff")
STAFF_FILE_GLOB = "staff_*.json"

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

MISSING = "brak danych w USOS"


def _latest_staff_file(staff_dir: str) -> str | None:
    matches = sorted(glob.glob(os.path.join(staff_dir, STAFF_FILE_GLOB)))
    return matches[-1] if matches else None


def _strip_html(text: str) -> str:
    text = HTML_TAG_PATTERN.sub(" ", text)
    return " ".join(text.split())


def _format_titles(titles: dict[str, str | None] | None) -> str:
    if not titles:
        return ""
    parts = [titles.get("before"), titles.get("after")]
    return " ".join(p for p in parts if p)


def _format_room(room: dict | None) -> str:
    if not room:
        return ""
    number = room.get("number")
    building = (room.get("building_name") or {}).get("pl")
    parts = [f"pokój {number}" if number else None, building]
    return ", ".join(p for p in parts if p)


def _format_positions(positions: list[dict] | None) -> str:
    if not positions:
        return ""
    formatted = []
    for entry in positions:
        position_name = ((entry.get("position") or {}).get("name") or {}).get("pl")
        faculty_name = ((entry.get("faculty") or {}).get("name") or {}).get("pl")
        if position_name and faculty_name:
            formatted.append(f"{position_name} ({faculty_name})")
        elif position_name:
            formatted.append(position_name)
    return "; ".join(formatted)


def _format_phones(phones: list[str] | None) -> str:
    if not phones:
        return ""
    return ", ".join(str(p).strip() for p in phones if str(p).strip())


def _employee_to_document(employee: dict) -> Document:
    full_name = " ".join(
        part for part in (employee.get("first_name"), employee.get("last_name")) if part
    )
    titles = _format_titles(employee.get("titles"))
    room = _format_room(employee.get("room"))
    office_hours_text = _strip_html(employee.get("office_hours_text") or "")
    interests_text = _strip_html(employee.get("interests_text") or "")
    positions = _format_positions(employee.get("employment_positions"))
    email = employee.get("email") or ""
    phones = _format_phones(employee.get("phone_numbers"))
    homepage_url = employee.get("homepage_url") or ""
    profile_url = employee.get("profile_url") or ""

    lines = [f"{titles} {full_name}".strip()]
    if positions:
        lines.append(f"Stanowisko: {positions}")
    lines.append(f"Pokoj: {room or MISSING}")
    lines.append(f"Dyzury: {office_hours_text or MISSING}")
    lines.append(f"E-mail: {email or MISSING}")
    lines.append(f"Telefon: {phones or MISSING}")
    if homepage_url:
        lines.append(f"Strona domowa: {homepage_url}")
    if interests_text:
        lines.append(f"Zainteresowania: {interests_text}")
    embed_text = "\n".join(lines)

    metadata = {
        "employee_id": employee.get("id"),
        "employee_name": full_name,
        "email": email,
        "phone": phones,
        "room": room,
        "office_hours": office_hours_text,
        "interests": interests_text,
        "homepage_url": homepage_url,
        "profile_url": profile_url,
        "employment_positions": positions,
    }

    return Document(
        id=make_id("usos", str(employee.get("id"))),
        source="usos",
        embed_text=embed_text,
        content_type="text",
        value=embed_text,
        metadata=metadata,
    )


def load_documents(staff_dir: str = STAFF_DIR, staff_file: str | None = None) -> list[Document]:
    """Wczytuje i normalizuje dataset pracownikow USOS do listy Document.

    Domyslnie bierze najnowszy plik staff_*.json z data/usos/staff/. Mozna
    tez wskazac konkretny plik przez staff_file (np. do testow).
    """
    path = staff_file or _latest_staff_file(staff_dir)
    if not path or not os.path.exists(path):
        print(f"[usos] Brak pliku datasetu w {staff_dir}, pomijam.")
        return []

    with open(path, "r", encoding="utf-8") as f:
        employees = json.load(f)

    return [_employee_to_document(employee) for employee in employees]
