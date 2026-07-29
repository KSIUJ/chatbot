"""
Konwersja danych z src/data/usos/scrape_staff.py do wspolnego schematu Document.

ZALOZENIA (zweryfikowane na realnym przebiegu scrape_staff.py z 2026-07-29,
208 pracownikow WMI - patrz PR):
- scrape_staff.py zapisuje jeden plik JSON na uruchomienie:
  data/usos/staff/staff_{fac_id}_{znacznik_czasu}.json - lista rekordow
  pracownikow w ksztalcie zwracanym przez normalize_employee(). Poniewaz
  kazde uruchomienie tworzy NOWY plik z wlasnym znacznikiem czasu, domyslnie
  bierzemy NAJNOWSZY plik pasujacy do wzorca (sortowanie po nazwie dziala,
  bo znacznik czasu jest w formacie ISO-podobnym %Y%m%dT%H%M%SZ) - nie
  laczymy danych z wielu przebiegow.
- Jeden pracownik = jeden Document (rekordy sa krotkie, nie wymagaja
  dzielenia na chunki jak dokumenty tekstowe z mordoru/stron).
- `titles` to NIE plaski string/lista, tylko dict {"before": "dr hab.",
  "after": "prof. UJ"} (oba pola bywaja null) - formatujemy jako
  "before after" pomijajac puste.
- `room` to NIE string, tylko dict {"number": ..., "building_name": {"pl":
  ..., "en": ...}, ...} albo null (u ~połowy pracownikow) - bierzemy numer +
  polska nazwa budynku.
- `employment_positions` to lista dictow {"position": {"name": {"pl": ...}},
  "faculty": {"name": {"pl": ...}}} (czasem >1 wpis - pracownik na kilku
  etatach/jednostkach) - formatujemy kazdy jako "stanowisko (jednostka)".
- `office_hours_text` bywa surowym HTML-em (np. "<b>Dyzur w sesji
  letniej</b>") - usuwamy tagi przed wrzuceniem do embed_text, zeby nie
  zaburzaly wyszukiwania/promptu.
"""

import glob
import json
import os
import re

from ..ingest.schema import Document, make_id

STAFF_DIR = os.path.join("data", "usos", "staff")
STAFF_FILE_GLOB = "staff_*.json"

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def _latest_staff_file(staff_dir: str) -> str | None:
    matches = sorted(glob.glob(os.path.join(staff_dir, STAFF_FILE_GLOB)))
    return matches[-1] if matches else None


def _strip_html(text: str) -> str:
    text = HTML_TAG_PATTERN.sub(" ", text)
    return " ".join(text.split())


def _format_titles(titles: dict | None) -> str:
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


def _format_positions(positions: list | None) -> str:
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

    lines = [f"{titles} {full_name}".strip()]
    if positions:
        lines.append(f"Stanowisko: {positions}")
    if room:
        lines.append(f"Pokoj: {room}")
    if office_hours_text:
        lines.append(f"Dyzury: {office_hours_text}")
    if email:
        lines.append(f"E-mail: {email}")
    if interests_text:
        lines.append(f"Zainteresowania: {interests_text}")
    embed_text = "\n".join(lines)

    metadata = {
        "employee_id": employee.get("id"),
        "employee_name": full_name,
        "email": email,
        "room": room,
        "office_hours": office_hours_text,
        "profile_url": employee.get("profile_url"),
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
