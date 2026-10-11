"""Rekordy pracownikow -> dokumenty indeksu: jedna karta na osobe.

Tekst do wyszukiwania to karta z dopisanym dopelniaczem imienia i nazwiska
("Odmiana: Jacka Cyranki") - pytania czesto uzywaja tej formy ("dyzury
Jacka Cyranki"); model dostaje sama karte."""

from __future__ import annotations

from ...core.documents import Document, make_id
from .dataset import StaffRecord
from .names import genitive

MISSING = "brak danych w USOS"


def full_name(record: StaffRecord) -> str:
    a = record.attributes
    return " ".join(part for part in (a.first_name, a.last_name) if part)


def _room(record: StaffRecord) -> str:
    room = record.attributes.room
    if room is None:
        return ""
    return ", ".join(part for part in (f"pokój {room.number}" if room.number else "", room.building) if part)


def _positions(record: StaffRecord) -> str:
    return "; ".join(f"{p.name} ({p.unit})" if p.unit else p.name for p in record.attributes.positions)


def staff_document(source: str, record: StaffRecord) -> Document:
    a = record.attributes
    name = full_name(record)
    titles = " ".join(t for t in (a.titles_before, a.titles_after) if t)
    room = _room(record)
    positions = _positions(record)
    phones = ", ".join(p.strip() for p in a.phones if p.strip())

    lines = [f"{titles} {name}".strip()]
    if positions:
        lines.append(f"Stanowisko: {positions}")
    lines.append(f"Pokoj: {room or MISSING}")
    lines.append(f"Dyzury: {a.office_hours or MISSING}")
    lines.append(f"E-mail: {a.email or MISSING}")
    lines.append(f"Telefon: {phones or MISSING}")
    if a.homepage_url:
        lines.append(f"Strona domowa: {a.homepage_url}")
    if a.interests:
        lines.append(f"Zainteresowania: {a.interests}")
    text = "\n".join(lines)
    declined = genitive(a.first_name, a.last_name)
    embed_text = f"{text}\nOdmiana: {declined}" if declined and declined != name else text

    return Document(
        id=make_id(source, a.usos_id),
        source=source,
        embed_text=embed_text,
        content_type="text",
        value=text,
        metadata={
            "employee_id": a.usos_id,
            "employee_name": name,
            "email": a.email,
            "phone": phones,
            "room": room,
            "office_hours": a.office_hours,
            "interests": a.interests,
            "homepage_url": a.homepage_url,
            "profile_url": record.url or "",
            "employment_positions": positions,
        },
    )
