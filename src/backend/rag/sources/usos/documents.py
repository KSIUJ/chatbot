"""Rekordy USOS -> dokumenty indeksu.

Pracownik to jedna karta na osobe (staff_document). Pozostale rodzaje
(entry_documents) sa dzielone na fragmenty wedlug naglowkow, a kazdy zaczyna
sie linia kontekstu z rodzajem i tytulem, np. "USOS › Przedmiot › Analiza
matematyczna 1 › Zajecia 2026/27Z".

W karcie pracownika tekst do wyszukiwania to karta z dopisanym dopelniaczem imienia i nazwiska
("Odmiana: Jacka Cyranki") - pytania czesto uzywaja tej formy ("dyzury
Jacka Cyranki"); model dostaje sama karte."""

from __future__ import annotations

from ...core.chunking import CONTEXT_SEPARATOR, chunk_markdown, context_line, make_splitter, with_context
from ...core.documents import Document, make_id
from .dataset import PageRecord, StaffRecord
from .names import genitive

MISSING = "brak danych w USOS"

STAFF_KIND = "staff"

# pierwszy element linii kontekstu fragmentu - rodzaj rekordu
KIND_LABELS = {
    "news": "USOS › Aktualności",
    "unit": "USOS › Jednostka",
    "course": "USOS › Przedmiot",
    "programme": "USOS › Studia",
    "calendar": "USOS › Kalendarz akademicki",
    "registration": "USOS › Rejestracje",
    "building": "USOS › Budynki i sale",
    "dormitory": "USOS › Akademiki",
}
PAGE_LABELS = {"usosweb": "USOSweb"}


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
            "kind": STAFF_KIND,
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


def _context_parts(record) -> tuple[str, ...]:
    if isinstance(record, PageRecord):
        return (PAGE_LABELS[record.attributes.section], *record.attributes.breadcrumbs)
    return (KIND_LABELS[record.kind],)


def _metadata(record) -> dict:
    """Pola rekordu przydatne w metadanych: identyfikatory i daty (bez list -
    metadane indeksu sa plaskie)."""
    metadata: dict = {}
    for key, value in record.attributes.model_dump(mode="json").items():
        if isinstance(value, list):
            # srednik: nazwiska z tytulami same zawieraja przecinki ("Jan Kowalski, prof. UJ")
            value = "; ".join(str(v) for v in value if isinstance(v, (str, int, float)))
        if value not in (None, ""):
            metadata[key] = value
    return metadata


def entry_documents(source: str, records: list) -> list[Document]:
    """Rekordy z trescia (wszystko poza pracownikiem) -> fragmenty wedlug
    naglowkow z linia kontekstu (rodzaj, okruszki, tytul, sekcja)."""
    splitter = make_splitter()
    documents: list[Document] = []
    for record in records:
        extra = _metadata(record)
        for index, chunk in enumerate(chunk_markdown(record.content, splitter)):
            context = context_line(*_context_parts(record), record.title, *chunk.section)
            text = with_context(context, chunk.text)
            documents.append(
                Document(
                    id=make_id(source, record.id, str(index)),
                    source=source,
                    embed_text=text,
                    content_type="text",
                    value=text,
                    metadata={
                        **extra,
                        "kind": record.kind,
                        "record_id": record.id,
                        "title": record.title,
                        "url": record.url or "",
                        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
                        "section": CONTEXT_SEPARATOR.join(chunk.section),
                        "chunk_index": index,
                    },
                )
            )
    return documents
