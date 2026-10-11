"""
Adapter starego wyjscia scrapera USOS (pipeline/scrapers/usos/scrape_staff.py)
do formatu usos - do czasu przebudowy scrapera.

- Kazde uruchomienie scrapera zapisuje nowy plik
  data/usos/staff/staff_{fac_id}_{%Y%m%dT%H%M%SZ}.json; brany jest tylko
  najnowszy (sortowanie po nazwie), bez laczenia przebiegow.
- Ksztalt pol z normalize_employee(): `titles` to {"before", "after"},
  `room` to {"number", "building_name": {"pl", ...}} albo null,
  `employment_positions` to lista {"position": {"name": {"pl"}}, "faculty":
  {"name": {"pl"}}}; `office_hours_text` bywa HTML-em, wiec tagi sa usuwane.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ...core.citations import http_url
from .dataset import Position, Room, StaffAttributes, StaffRecord

LEGACY_DIR = Path("usos") / "staff"
STAFF_FILE_GLOB = "staff_*.json"

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def latest_staff_file(data_dir: Path) -> Path | None:
    matches = sorted((data_dir / LEGACY_DIR).glob(STAFF_FILE_GLOB))
    return matches[-1] if matches else None


def strip_html(text: str) -> str:
    text = HTML_TAG_PATTERN.sub(" ", text)
    return " ".join(text.split())


def _pl(value: object) -> str:
    return ((value or {}).get("name") or {}).get("pl") or "" if isinstance(value, dict) else ""


def to_record(employee: dict) -> StaffRecord:
    titles = employee.get("titles") or {}
    room = employee.get("room")
    positions = [
        Position(name=_pl(entry.get("position")), unit=_pl(entry.get("faculty")))
        for entry in employee.get("employment_positions") or []
        if _pl(entry.get("position"))
    ]
    first, last = employee.get("first_name") or "", employee.get("last_name") or ""
    return StaffRecord(
        id=str(employee.get("id")),
        kind="staff",
        title=" ".join(p for p in (first, last) if p),
        url=http_url(employee.get("profile_url")),
        attributes=StaffAttributes(
            usos_id=str(employee.get("id")),
            first_name=first,
            last_name=last,
            titles_before=titles.get("before") or "",
            titles_after=titles.get("after") or "",
            positions=positions,
            room=Room(
                number=str(room.get("number") or ""), building=(room.get("building_name") or {}).get("pl") or ""
            )
            if room
            else None,
            office_hours=strip_html(employee.get("office_hours_text") or ""),
            interests=strip_html(employee.get("interests_text") or ""),
            email=employee.get("email") or "",
            phones=[str(p).strip() for p in employee.get("phone_numbers") or [] if str(p).strip()],
            homepage_url=employee.get("homepage_url") or "",
        ),
    )


def convert(data_dir: Path) -> list[StaffRecord] | None:
    """Rekordy z najnowszego data/usos/staff/staff_*.json; None = brak pliku."""
    path = latest_staff_file(data_dir)
    if path is None:
        return None
    return [to_record(employee) for employee in json.loads(path.read_text(encoding="utf-8"))]
