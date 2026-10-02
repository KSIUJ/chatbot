"""Endpointy zalacznikow (za nginxem pod /api/*).

    POST   /attachments       surowe cialo = zawartosc pliku, nazwa w naglowku
                              X-Filename (procentowo zakodowana, jak
                              encodeURIComponent) -> {id, name, size, type, pages, chars}
    GET    /attachments/{id}  pobranie pliku (tylko wlasciciel)
    DELETE /attachments/{id}  usuniecie niewyslanego zalacznika

Plik jest przesylany jako surowe cialo zapytania, a nie multipart: nie
potrzeba zaleznosci python-multipart, a cialo da sie czytac strumieniowo
z twardym limitem - za duzy plik jest odrzucany od razu (po Content-Length)
albo w trakcie (bez zapisywania reszty).

Kolejnosc przy wysylaniu: najwyzej MAX_CONCURRENT_UPLOADS wysylan naraz na
osobe, wylacznik czatu, limity z panelu, Content-Length, wolne miejsce na
dysku, limit bajtow niewyslanych plikow osoby, dzienny limit plikow,
odbior ciala (najwyzej UPLOAD_DEADLINE_SECONDS) do pliku .part pod losowa
nazwa, rodzaj po zawartosci, wyciagniecie tekstu, heurystyka prompt
injection na tekscie, wiersz w bazie.

Dzienny limit jest zuzywany przed zapisem i wraca TYLKO po bledzie serwera.
Plik odrzucony z wlasnej winy (za duzy, zly typ, nieczytelny, za wolno
wysylany) albo przerwany przez klienta zuzywa miejsce - inaczej wysylanie
zlosliwych plikow (parsowanie kosztuje CPU) byloby darmowe. Plik .part
znika w kazdym przypadku, takze po anulowaniu.
"""

from __future__ import annotations

import logging
import math
import shutil
from pathlib import Path
from typing import Final
from urllib.parse import unquote

import anyio
from anyio import to_thread
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from ..auth.dependencies import require_member
from ..database import get_db
from ..limits.settings import MAX_IMAGE_MB, AttachmentLimits, ensure_chat_enabled, get_attachment_limits
from ..limits.usage import (
    AttachmentLimitExceeded,
    Clock,
    Reservation,
    consume_attachment,
    get_clock,
    refund_attachment,
)
from ..models import User
from ..security.injection import detect_injection
from . import storage
from .errors import (
    ATTACHMENT_SENT,
    ATTACHMENTS_DISABLED,
    ATTACHMENTS_LIMITED,
    ATTACHMENTS_STORAGE_FULL,
    EMPTY_FILE,
    FILE_TOO_LARGE,
    STORAGE_UNAVAILABLE,
    UNREADABLE_FILE,
    UNSUPPORTED_TYPE,
    UPLOAD_TIMEOUT,
    UPLOADS_BUSY,
    AttachmentError,
    not_found,
)
from .extract import UnreadableFile, extract
from .schemas import AttachmentUploadResponse
from .service import create_attachment, delete_unsent, get_owned, unsent_bytes
from .slots import UploadSlots
from .sniff import IMAGE_KINDS, detect_kind, display_name

logger = logging.getLogger(__name__)

MB: Final = 1024 * 1024
FILENAME_HEADER: Final = "X-Filename"
# dluzsza nazwa w naglowku jest obcinana przed dekodowaniem
MAX_RAW_NAME_LENGTH: Final = 1024
# obrazy maja nizszy limit - tyle przyjmuje Claude API na jeden obraz
MAX_IMAGE_BYTES = MAX_IMAGE_MB * MB
# rownoczesne wysylania jednej osoby (frontend wysyla najwyzej tyle naraz)
MAX_CONCURRENT_UPLOADS: Final = 2
# caly odbior pliku (ochrona przed "slowloris" trzymajacym polaczenie)
UPLOAD_DEADLINE_SECONDS = 120.0
# ponizej tylu wolnych bajtow na wolumenie zalacznikow nie przyjmujemy plikow
MIN_FREE_BYTES = 500 * MB

UPLOAD_SLOTS = UploadSlots(MAX_CONCURRENT_UPLOADS)

__all__ = ["UPLOAD_SLOTS", "UploadSlots", "router"]

router = APIRouter(tags=["attachments"])


def _too_large(max_bytes: int) -> AttachmentError:
    max_mb = max_bytes // MB
    return AttachmentError(
        413, FILE_TOO_LARGE, f"Plik jest za duży (limit {max_mb} MB).", extra={"max_mb": max_mb}
    )


def _limited(exc: AttachmentLimitExceeded) -> AttachmentError:
    retry_after = max(1, math.ceil((exc.reset_at - exc.checked_at).total_seconds()))
    return AttachmentError(
        429,
        ATTACHMENTS_LIMITED,
        f"Wykorzystano dzienny limit załączników ({exc.limit}). Limit odnowi się o północy.",
        extra={"limit": exc.limit, "reset_at": exc.reset_at.isoformat()},
        headers={"Retry-After": str(retry_after)},
    )


def _declared_length(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None or not raw.strip().isdigit():
        return None
    return int(raw)


def unsent_cap(limits: AttachmentLimits) -> int:
    """Ile bajtow niewyslanych plikow moze naraz miec jedna osoba: tyle,
    ile da sie dolaczyc do jednego pytania."""
    return limits.max_files_per_message * limits.max_file_mb * MB


def _storage_full() -> AttachmentError:
    return AttachmentError(
        429, ATTACHMENTS_STORAGE_FULL,
        "Masz za dużo niewysłanych plików. Wyślij pytanie albo usuń część plików.",
    )


def _check_free_space() -> None:
    root = storage.attachments_dir()
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < MIN_FREE_BYTES:
        logger.error("attachments volume %s is almost full - refusing uploads", root)
        raise AttachmentError(
            507, STORAGE_UNAVAILABLE, "Brak miejsca na serwerze na nowe pliki. Spróbuj później."
        )


def _start_upload(
    db: Session, user_id: str, now_clock: Clock, declared: int | None
) -> tuple[AttachmentLimits, Reservation]:
    """Sprawdzenia przed odczytem ciala i zuzycie miejsca w dziennym limicie."""
    ensure_chat_enabled(db)
    limits = get_attachment_limits(db)
    if limits.max_per_day <= 0:
        raise AttachmentError(403, ATTACHMENTS_DISABLED, "Załączniki są wyłączone przez zarząd KSI.")
    max_bytes = limits.max_file_mb * MB
    if declared is not None and declared > max_bytes:
        raise _too_large(max_bytes)
    _check_free_space()
    pending = unsent_bytes(db, user_id)
    if pending >= unsent_cap(limits) or (declared is not None and pending + declared > unsent_cap(limits)):
        raise _storage_full()
    try:
        reservation = consume_attachment(db, user_id, now_clock(), limits.max_per_day)
    except AttachmentLimitExceeded as exc:
        raise _limited(exc) from None
    return limits, reservation


async def _receive(request: Request, target: Path, max_bytes: int) -> int:
    """Zapisuje cialo zapytania do pliku; przerywa po przekroczeniu limitu."""
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        async for chunk in request.stream():
            size += len(chunk)
            if size > max_bytes:
                raise _too_large(max_bytes)
            if chunk:
                await to_thread.run_sync(handle.write, chunk)
    return size


def _finish_upload(
    db: Session, user_id: str, part: Path, key: str, raw_name: str | None, limits: AttachmentLimits, size: int
) -> AttachmentUploadResponse:
    """Rodzaj po zawartosci, tekst, heurystyka i wiersz w bazie."""
    if size == 0:
        raise AttachmentError(422, EMPTY_FILE, "Plik jest pusty.")
    kind = detect_kind(part)
    if kind is None or kind not in limits.allowed_types:
        raise AttachmentError(415, UNSUPPORTED_TYPE, "Ten rodzaj pliku nie jest obsługiwany.")
    image_cap = min(MAX_IMAGE_BYTES, limits.max_file_mb * MB)
    if kind in IMAGE_KINDS and size > image_cap:
        raise _too_large(image_cap)
    # bez Content-Length limit niewyslanych plikow sprawdzamy dopiero tu
    if unsent_bytes(db, user_id) + size > unsent_cap(limits):
        raise _storage_full()
    try:
        extraction = extract(part, kind)
    except UnreadableFile as exc:
        logger.info("rejected unreadable %s upload of user %s: %s", kind, user_id, exc)
        raise AttachmentError(
            422, UNREADABLE_FILE, "Nie udało się odczytać pliku (uszkodzony albo zabezpieczony hasłem)."
        ) from None
    final = storage.path_for(key)
    part.replace(final)
    try:
        row = create_attachment(
            db,
            user_id=user_id,
            name=display_name(raw_name, kind),
            kind=kind,
            size=size,
            storage_key=key,
            extraction=extraction,
            injection_rules=detect_injection(extraction.text or ""),
        )
    except Exception:
        db.rollback()
        storage.remove_files([key])
        raise
    return AttachmentUploadResponse(
        id=row.id,
        name=row.name,
        size=row.size,
        type=kind,
        pages=row.pages,
        chars=len(row.text) if row.text is not None else None,
    )


def _raw_name(request: Request) -> str | None:
    raw = request.headers.get(FILENAME_HEADER)
    if raw is None:
        return None
    return unquote(raw[:MAX_RAW_NAME_LENGTH], errors="replace")


def _discard_part(part: Path) -> None:
    """Usuwa plik tymczasowy (po udanym wysylaniu juz go nie ma)."""
    try:
        part.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("deleting upload part %s failed: %s", part.name, exc)


def _refund_after_server_error(db: Session, reservation: Reservation) -> None:
    """Zwrot miejsca w dziennym limicie - tylko po bledzie serwera."""
    db.rollback()
    try:
        refund_attachment(db, reservation)
    except Exception:
        db.rollback()
        logger.exception("refunding attachment slot failed (user %s)", reservation.user_id)


async def _store_upload(
    request: Request, db: Session, user_id: str, limits: AttachmentLimits, reservation: Reservation
) -> AttachmentUploadResponse:
    """Odbior, sprawdzenie i zapis pliku. Bledy pliku i klienta (AttachmentError,
    rozlaczenie, anulowanie) nie oddaja miejsca w limicie; blad serwera oddaje.
    Plik .part znika zawsze (finally obejmuje tez anulowanie)."""
    key = storage.new_storage_key()
    part = storage.path_for(key + storage.PART_SUFFIX)
    server_error = False
    try:
        try:
            with anyio.fail_after(UPLOAD_DEADLINE_SECONDS):
                size = await _receive(request, part, limits.max_file_mb * MB)
        except TimeoutError:
            raise AttachmentError(408, UPLOAD_TIMEOUT, "Wysyłanie pliku trwało zbyt długo.") from None
        return await run_in_threadpool(_finish_upload, db, user_id, part, key, _raw_name(request), limits, size)
    except (AttachmentError, ClientDisconnect):
        raise
    except Exception:
        server_error = True
        raise
    finally:
        _discard_part(part)
        if server_error:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(_refund_after_server_error, db, reservation)


@router.post("/attachments", status_code=201, response_model=AttachmentUploadResponse)
async def upload_attachment(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
    clock: Clock = Depends(get_clock),
) -> AttachmentUploadResponse:
    """Wysyla jeden plik (surowe cialo). Bledy: 403 attachments_disabled,
    408 upload_timeout, 413 file_too_large, 415 unsupported_type,
    422 empty_file / unreadable_file, 429 attachments_limited / uploads_busy /
    attachments_storage_full, 503 chat_disabled, 507 storage_unavailable."""
    if not UPLOAD_SLOTS.try_acquire(user.id):
        raise AttachmentError(429, UPLOADS_BUSY, "Za dużo plików wysyłanych naraz. Poczekaj chwilę.")
    try:
        limits, reservation = await run_in_threadpool(
            _start_upload, db, user.id, clock, _declared_length(request)
        )
        return await _store_upload(request, db, user.id, limits, reservation)
    finally:
        UPLOAD_SLOTS.release(user.id)


@router.get("/attachments/{attachment_id}", response_class=FileResponse)
def download_attachment(
    attachment_id: str, db: Session = Depends(get_db), user: User = Depends(require_member)
) -> FileResponse:
    """Plik wlasciciela jako pobranie (nigdy wyswietlany w przegladarce)."""
    row = get_owned(db, user.id, attachment_id)
    if row is None:
        raise not_found()
    path = storage.path_for(row.storage_key)
    if not path.is_file():
        logger.warning("attachment %s has no file on disk", row.id)
        raise not_found()
    return FileResponse(
        path,
        media_type=row.mime,
        filename=row.name,
        content_disposition_type="attachment",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    attachment_id: str, db: Session = Depends(get_db), user: User = Depends(require_member)
) -> Response:
    """Usuwa niewyslany zalacznik; wyslany znika tylko razem z rozmowa (409)."""
    row = get_owned(db, user.id, attachment_id)
    if row is None:
        raise not_found()
    if row.conversation_id is not None:
        raise AttachmentError(409, ATTACHMENT_SENT, "Wysłany załącznik usuwa się razem z rozmową.")
    delete_unsent(db, row)
    return Response(status_code=204)
