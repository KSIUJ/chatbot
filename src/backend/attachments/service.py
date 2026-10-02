"""Zalaczniki w bazie: zapis po wyslaniu pliku, dobor zalacznikow do tury
czatu, przypinanie do pytania po odpowiedzi i kasowanie (z rozmowa albo
niewyslanych po UNSENT_RETENTION).

Zasada "najpierw odpowiedz": zalacznik jest przypinany do pytania dopiero
w save_exchange (chat.py), razem z zapisem odpowiedzi. Blad modelu zostawia
go niewyslanym - mozna ponowic pytanie z tym samym plikiem.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..limits.settings import AttachmentType
from ..llm.attachments import PromptAttachment
from ..llm.images import ImageInput
from ..models import Attachment, Conversation, Message, MessageRole
from . import storage
from .errors import IMAGES_UNSUPPORTED, TOO_MANY_FILES, AttachmentError, not_found
from .extract import Extraction
from .sniff import IMAGE_KINDS, MIME_TYPES

logger = logging.getLogger(__name__)

# niewyslane pliki (np. porzucone w polu pytania) kasujemy po dobie
UNSENT_RETENTION = timedelta(hours=24)
# prefiks regul heurystyki znalezionych w tresci pliku (incydenty)
ATTACHMENT_RULE_PREFIX = "attachment:"
# obrazy z wczesniejszych pytan wysylane ponownie: najwyzej tyle najnowszych
MAX_EARLIER_IMAGES = 3
# lacznie obrazow w jednym zapytaniu do modelu (biezace + wczesniejsze) -
# z zapasem ponizej limitow API (Claude: 32 MB na zapytanie po base64)
MAX_TOTAL_IMAGE_BYTES = 15 * 1024 * 1024


@dataclass(frozen=True)
class TurnAttachments:
    """Zalaczniki jednej tury czatu."""
    # dla modelu (tekst, obrazy), w kolejnosci wyslania
    prompt: tuple[PromptAttachment, ...] = ()
    # niewyslane zalaczniki do przypiecia do pytania po odpowiedzi
    link_ids: tuple[str, ...] = ()
    # reguly heurystyki z tresci plikow, z prefiksem "attachment:"
    injection_rules: tuple[str, ...] = ()


NO_ATTACHMENTS = TurnAttachments()


# --- zapis i odczyt ------------------------------------------------------------------

def create_attachment(
    db: Session,
    *,
    user_id: str,
    name: str,
    kind: AttachmentType,
    size: int,
    storage_key: str,
    extraction: Extraction,
    injection_rules: Sequence[str],
) -> Attachment:
    """Zapisuje niewyslany zalacznik i commituje."""
    row = Attachment(
        user_id=user_id,
        name=name,
        kind=kind,
        mime=MIME_TYPES[kind],
        size=size,
        storage_key=storage_key,
        text=extraction.text,
        pages=extraction.pages,
        ocr=extraction.ocr,
        injection_rules=list(injection_rules),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_owned(db: Session, user_id: str, attachment_id: str) -> Attachment | None:
    """Zalacznik uzytkownika; cudzy wyglada jak nieistniejacy (None)."""
    row = db.get(Attachment, attachment_id, populate_existing=True)
    if row is None or row.user_id != user_id:
        return None
    return row


def unsent_bytes(db: Session, user_id: str) -> int:
    """Suma rozmiarow niewyslanych zalacznikow osoby (limit miejsca na dysku)."""
    total = db.execute(
        select(func.coalesce(func.sum(Attachment.size), 0)).where(
            Attachment.user_id == user_id, Attachment.conversation_id.is_(None)
        )
    ).scalar_one()
    return int(total)


def delete_unsent(db: Session, row: Attachment) -> None:
    """Kasuje niewyslany zalacznik (wiersz i plik) i commituje."""
    key = row.storage_key
    db.delete(row)
    db.commit()
    storage.remove_files([key])


def attachments_by_message(db: Session, conversation_id: str) -> dict[str, list[Attachment]]:
    """Zalaczniki rozmowy pogrupowane po pytaniu (message_id)."""
    stmt = (
        select(Attachment)
        .where(Attachment.conversation_id == conversation_id, Attachment.message_id.is_not(None))
        .order_by(Attachment.created_at, Attachment.id)
    )
    grouped: dict[str, list[Attachment]] = {}
    for row in db.execute(stmt).scalars():
        grouped.setdefault(str(row.message_id), []).append(row)
    return grouped


# --- tura czatu ------------------------------------------------------------------------

def _latest_question_id(db: Session, conversation_id: str) -> str | None:
    stmt = (
        select(Message.id)
        .where(Message.conversation_id == conversation_id, Message.role == MessageRole.USER)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _replayed(db: Session, user_id: str, conversation_id: str) -> list[Attachment]:
    """Zalaczniki ostatniego pytania rozmowy (regeneracja je powtarza)."""
    question_id = _latest_question_id(db, conversation_id)
    if question_id is None:
        return []
    stmt = (
        select(Attachment)
        .where(Attachment.message_id == question_id, Attachment.user_id == user_id)
        .order_by(Attachment.created_at, Attachment.id)
    )
    return list(db.execute(stmt).scalars())


def _requested(db: Session, user_id: str, conversation_id: str, ids: Sequence[str]) -> list[Attachment]:
    """Zalaczniki o podanych id, w kolejnosci podania.

    Raises:
        AttachmentError: 404, gdy ktorys nie istnieje, jest cudzy albo
            nalezy do innej rozmowy.
    """
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return []
    stmt = select(Attachment).where(Attachment.id.in_(wanted), Attachment.user_id == user_id)
    found = {row.id: row for row in db.execute(stmt).scalars()}
    rows: list[Attachment] = []
    for attachment_id in wanted:
        row = found.get(attachment_id)
        if row is None or row.conversation_id not in (None, conversation_id):
            raise not_found()
        rows.append(row)
    return rows


def _read_image(row: Attachment) -> ImageInput | None:
    try:
        return ImageInput(row.mime, storage.path_for(row.storage_key).read_bytes())
    except (OSError, ValueError) as exc:
        logger.warning("attachment file %s unavailable: %s", row.id, exc)
        return None


def _prompt_attachment(row: Attachment, *, image: ImageInput | None = None, earlier: bool = False) -> PromptAttachment:
    return PromptAttachment(
        name=row.name, kind=row.kind, text=row.text, pages=row.pages, image=image, earlier=earlier, ocr=row.ocr,
    )


def _current_prompt(row: Attachment) -> PromptAttachment:
    """Plik biezacego pytania; brak pliku obrazu na dysku = 404."""
    image = None
    if row.kind in IMAGE_KINDS:
        image = _read_image(row)
        if image is None:
            raise not_found()
    return _prompt_attachment(row, image=image)


def _earlier(db: Session, user_id: str, conversation_id: str, exclude: set[str]) -> list[Attachment]:
    """Pliki wyslane wczesniej w tej rozmowie (przypiete do pytan), od
    najnowszych, bez plikow biezacego pytania."""
    stmt = (
        select(Attachment)
        .where(
            Attachment.conversation_id == conversation_id,
            Attachment.user_id == user_id,
            Attachment.message_id.is_not(None),
        )
        .order_by(Attachment.created_at.desc(), Attachment.id.desc())
    )
    return [row for row in db.execute(stmt).scalars() if row.id not in exclude]


def _earlier_prompts(
    rows: Sequence[Attachment], images_supported: bool, image_bytes_used: int
) -> list[PromptAttachment]:
    """Wczesniejsze pliki dla modelu. Obrazy tylko dla dostawcow z obsluga
    obrazow: najwyzej MAX_EARLIER_IMAGES najnowszych i lacznie (z obrazami
    biezacego pytania) najwyzej MAX_TOTAL_IMAGE_BYTES - pozostale obrazy sa
    tylko wymienione z nazwy. Bez bledu images_unsupported."""
    prompts: list[PromptAttachment] = []
    images = 0
    used = image_bytes_used
    for row in rows:
        image = None
        fits = images < MAX_EARLIER_IMAGES and used + row.size <= MAX_TOTAL_IMAGE_BYTES
        if row.kind in IMAGE_KINDS and images_supported and fits:
            image = _read_image(row)
            if image is not None:
                images += 1
                used += len(image.data)
        prompts.append(_prompt_attachment(row, image=image, earlier=True))
    return prompts


def _rules(rows: Sequence[Attachment]) -> tuple[str, ...]:
    rules = (f"{ATTACHMENT_RULE_PREFIX}{rule}" for row in rows for rule in (row.injection_rules or []))
    return tuple(dict.fromkeys(rules))


def resolve_turn_attachments(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
    requested_ids: Sequence[str],
    regenerate: bool,
    max_files: int,
    images_supported: bool,
) -> TurnAttachments:
    """Zalaczniki pytania: przy regeneracji te z powtarzanego pytania, plus
    podane id (niewyslane albo juz w tej rozmowie), a za nimi pliki wyslane
    wczesniej w rozmowie (od najnowszych). Wolane przed zuzyciem limitu
    pytan i przed modelem. Limity, images_unsupported i reguly heurystyki
    dotycza tylko plikow biezacego pytania - wczesniejsze byly sprawdzone
    przy wyslaniu, wiec nie zakladaja nowych incydentow.

    Raises:
        AttachmentError: 404 attachment_not_found, 422 too_many_files albo
            422 images_unsupported (obraz w biezacym pytaniu, dostawca bez
            obslugi obrazow).
    """
    replayed = _replayed(db, user_id, conversation_id) if regenerate else []
    requested = _requested(db, user_id, conversation_id, requested_ids)
    known = {row.id for row in replayed}
    rows = [*replayed, *(row for row in requested if row.id not in known)]
    earlier_rows = _earlier(db, user_id, conversation_id, {row.id for row in rows})
    if not rows and not earlier_rows:
        return NO_ATTACHMENTS
    if len(rows) > max_files:
        raise AttachmentError(
            422, TOO_MANY_FILES, f"Do jednego pytania możesz dołączyć najwyżej {max_files} plików.",
            extra={"max_files": max_files},
        )
    if not images_supported and any(row.kind in IMAGE_KINDS for row in rows):
        raise AttachmentError(
            422, IMAGES_UNSUPPORTED, "Obecny model nie obsługuje obrazów. Usuń obrazy z pytania.",
        )
    current = [_current_prompt(row) for row in rows]
    current_image_bytes = sum(len(item.image.data) for item in current if item.image is not None)
    return TurnAttachments(
        prompt=(*current, *_earlier_prompts(earlier_rows, images_supported, current_image_bytes)),
        link_ids=tuple(row.id for row in rows if row.conversation_id is None),
        injection_rules=_rules(rows),
    )


def link_attachments(
    db: Session, user_id: str, conversation_id: str, message_id: str, attachment_ids: Sequence[str]
) -> None:
    """Przypina niewyslane zalaczniki do zapisanego pytania. Bez commita -
    commituje zapis odpowiedzi. Zalacznik usuniety albo wyslany w miedzyczasie
    gdzie indziej jest pomijany."""
    if not attachment_ids:
        return
    db.execute(
        update(Attachment)
        .where(
            Attachment.id.in_(list(attachment_ids)),
            Attachment.user_id == user_id,
            Attachment.conversation_id.is_(None),
        )
        .values(conversation_id=conversation_id, message_id=message_id)
        .execution_options(synchronize_session=False)
    )


# --- kasowanie ---------------------------------------------------------------------------
# Zalaczniki rozmow kasuje history.py (delete_conversation_attachments) razem
# z rozmowa; tu sprzatanie niewyslanych i osieroconych.

def purge_stale_attachments(db: Session, now: datetime | None = None) -> int:
    """Zadanie sprzatajace: niewyslane zalaczniki starsze niz UNSENT_RETENTION,
    wiersze rozmow, ktorych juz nie ma, i zablakane pliki bez wiersza.
    Zwraca liczbe usunietych wierszy i plikow."""
    cutoff = (now or datetime.now(timezone.utc)) - UNSENT_RETENTION
    stale = (
        (Attachment.conversation_id.is_(None) & (Attachment.created_at < cutoff))
        | (
            Attachment.conversation_id.is_not(None)
            & Attachment.conversation_id.not_in(select(Conversation.id))
        )
    )
    keys = list(db.execute(select(Attachment.storage_key).where(stale)).scalars())
    db.execute(delete(Attachment).where(stale).execution_options(synchronize_session=False))
    db.commit()
    storage.remove_files(keys)
    known = set(db.execute(select(Attachment.storage_key)).scalars())
    return len(keys) + storage.sweep_stray_files(known, cutoff)
