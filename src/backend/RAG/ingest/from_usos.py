"""
Konwersja danych z src/data/usos/scrape_staff.py do wspolnego schematu Document.

ZALOZENIA (do zweryfikowania, patrz PR):
- scrape_staff.py zapisuje jeden plik JSON na uruchomienie:
  data/usos/staff/staff_{fac_id}_{znacznik_czasu}.json - lista rekordow
  pracownikow w ksztalcie zwracanym przez normalize_employee() (id,
  first_name, last_name, titles, email, phone_numbers, room, profile_url,
  homepage_url, office_hours/office_hours_text, interests/interests_text,
  employment_positions). Poniewaz kazde uruchomienie tworzy NOWY plik z
  wlasnym znacznikiem czasu, domyslnie bierzemy NAJNOWSZY plik pasujacy do
  wzorca (sortowanie po nazwie dziala, bo znacznik czasu jest w formacie
  ISO-podobnym %Y%m%dT%H%M%SZ) - nie laczymy danych z wielu przebiegow.
- Jeden pracownik = jeden Document (rekordy sa krotkie, nie wymagaja
  dzielenia na chunki jak dokumenty tekstowe z mordoru/stron).
- Brak przykladowych danych w repo (tylko data/usos/.gitkeep) w momencie
  pisania tego modulu - powyzsze zalozenia oparte sa wylacznie na kodzie
  scrape_staff.py, nie na realnym pliku wyjsciowym. Do zweryfikowania po
  pierwszym realnym uruchomieniu scrapera.
"""

import glob
import json
import os

from ..ingest.schema import Document, make_id

STAFF_DIR = os.path.join("data", "usos", "staff")
STAFF_FILE_GLOB = "staff_*.json"


def _latest_staff_file(staff_dir: str) -> str | None:
    matches = sorted(glob.glob(os.path.join(staff_dir, STAFF_FILE_GLOB)))
    return matches[-1] if matches else None


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify(v) for v in value if v)
    if isinstance(value, dict):
        return ", ".join(str(v) for v in value.values() if v)
    return str(value)


def _employee_to_document(employee: dict) -> Document:
    full_name = " ".join(
        part for part in (employee.get("first_name"), employee.get("last_name")) if part
    )
    titles = _stringify(employee.get("titles"))
    room = employee.get("room") or ""
    office_hours_text = employee.get("office_hours_text") or ""
    interests_text = employee.get("interests_text") or ""
    positions = _stringify(employee.get("employment_positions"))
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
