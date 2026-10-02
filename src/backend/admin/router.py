"""Panel administratora (grupa OIDC_ADMIN_GROUP): limity i diagnostyka.

Za nginxem jest pod /api/* (nginx obcina /api). Przeglad zgloszen i
incydentow ma wlasne endpointy (/admin/feedback*, /admin/incidents*).

    GET    /admin/settings           -> globalne limity (pytania, zalaczniki) i wylacznik czatu
    PUT    /admin/settings           -> zmiana limitow i/lub wylacznika czatu
    GET    /admin/users?q=           -> wyszukiwarka z dzisiejszym zuzyciem
    PUT    /admin/users/{id}/limit   -> wyjatek: wlasny limit albo bez limitu
    DELETE /admin/users/{id}/limit   -> powrot do limitu globalnego
    GET    /admin/diagnostics        -> stan modelu, uzycie, RAG, baza i dysk
                                        (cache ~15 s, ?refresh=1 liczy od nowa)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth.dependencies import require_admin
from ..database import get_db
from ..limits.settings import (
    ALL_ATTACHMENT_TYPES,
    AttachmentLimits,
    ChatAvailability,
    LimitSettings,
    get_chat_availability,
    get_default_limits,
    get_limit_settings,
    save_chat_availability,
    save_limit_settings,
)
from ..limits.usage import Clock, clear_user_limit, get_clock, set_user_limit, usage_day
from ..models import User
from .diagnostics import (
    DiagnosticsCache,
    DiagnosticsConfig,
    collect_diagnostics,
    get_diagnostics_cache,
    get_diagnostics_config,
)
from .schemas import (
    MAX_QUERY_LENGTH,
    AdminSettingsResponse,
    AdminSettingsUpdate,
    AdminUserItem,
    AdminUserPage,
    DiagnosticsResponse,
    LimitSettingsModel,
    UserLimitRequest,
    ranges_model,
)
from .users import search_users, user_item

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Odpowiedzi zawieraja dane osob - nie moga zostac w cache.
_NO_STORE = {"Cache-Control": "no-store"}

router = APIRouter(prefix="/admin", tags=["admin"])


def _settings_response(settings: LimitSettings, availability: ChatAvailability) -> AdminSettingsResponse:
    current = LimitSettingsModel.from_settings(settings)
    return AdminSettingsResponse(
        daily_question_limit=current.daily_question_limit,
        attachments=current.attachments,
        chat_enabled=availability.enabled,
        chat_disabled_message=availability.message,
        defaults=LimitSettingsModel.from_settings(get_default_limits()),
        available_types=list(ALL_ATTACHMENT_TYPES),
        ranges=ranges_model(),
    )


@router.get("/settings", response_model=AdminSettingsResponse)
def admin_get_settings(
    response: Response,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminSettingsResponse:
    """Obowiazujace globalne limity, wylacznik czatu, wartosci domyslne z env i zakresy."""
    response.headers.update(_NO_STORE)
    return _settings_response(get_limit_settings(db), get_chat_availability(db))


@router.put("/settings", response_model=AdminSettingsResponse)
def admin_put_settings(
    payload: AdminSettingsUpdate,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminSettingsResponse:
    """Zmienia limity (wszystkie naraz) i/lub wylacznik czatu z komunikatem;
    pominiete pola zostaja bez zmian (zakresy sprawdza schemat)."""
    response.headers.update(_NO_STORE)
    if payload.daily_question_limit is not None and payload.attachments is not None:
        settings = LimitSettings(
            daily_question_limit=payload.daily_question_limit,
            attachments=AttachmentLimits(
                max_file_mb=payload.attachments.max_file_mb,
                max_files_per_message=payload.attachments.max_files_per_message,
                max_per_day=payload.attachments.max_per_day,
                allowed_types=tuple(payload.attachments.allowed_types),
            ),
        )
        save_limit_settings(db, settings, admin.id)
        logger.info(
            "admin %s changed global limits: %s",
            admin.id, payload.model_dump(include={"daily_question_limit", "attachments"}),
        )
    if payload.chat_enabled is not None or payload.sets_message:
        save_chat_availability(
            db,
            enabled=payload.chat_enabled,
            message=payload.chat_disabled_message,
            sets_message=payload.sets_message,
            admin_id=admin.id,
        )
    return _settings_response(get_limit_settings(db), get_chat_availability(db))


@router.get("/users", response_model=AdminUserPage)
def admin_list_users(
    response: Response,
    q: str | None = Query(None, max_length=MAX_QUERY_LENGTH),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    _admin: User = Depends(require_admin),
) -> AdminUserPage:
    """Uzytkownicy wg nazwy; q szuka w imieniu i nazwisku, loginie i emailu."""
    response.headers.update(_NO_STORE)
    global_limit = get_limit_settings(db).daily_question_limit
    items, total = search_users(db, q, usage_day(clock()), global_limit, limit, offset)
    return AdminUserPage(items=items, total=total, limit=limit, offset=offset)


def _get_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.put("/users/{user_id}/limit", response_model=AdminUserItem)
def admin_put_user_limit(
    user_id: str,
    payload: UserLimitRequest,
    response: Response,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    admin: User = Depends(require_admin),
) -> AdminUserItem:
    """Nadaje albo zmienia wyjatek osoby; 404 dla nieznanego konta."""
    response.headers.update(_NO_STORE)
    user = _get_user(db, user_id)
    daily_limit = None if payload.unlimited else payload.daily_limit
    set_user_limit(db, user.id, daily_limit=daily_limit, note=payload.note, admin_id=admin.id)
    logger.info("admin %s set daily limit of user %s to %s", admin.id, user.id, daily_limit)
    return user_item(db, user, usage_day(clock()), get_limit_settings(db).daily_question_limit)


@router.delete("/users/{user_id}/limit", status_code=204)
def admin_delete_user_limit(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Response:
    """Usuwa wyjatek osoby (idempotentnie); 404 dla nieznanego konta."""
    user = _get_user(db, user_id)
    if clear_user_limit(db, user.id):
        logger.info("admin %s removed daily limit override of user %s", admin.id, user.id)
    return Response(status_code=204, headers=_NO_STORE)


@router.get("/diagnostics", response_model=DiagnosticsResponse)
def admin_diagnostics(
    response: Response,
    refresh: bool = False,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    config: DiagnosticsConfig = Depends(get_diagnostics_config),
    cache: DiagnosticsCache[DiagnosticsResponse] = Depends(get_diagnostics_cache),
    _admin: User = Depends(require_admin),
) -> DiagnosticsResponse:
    """Stan modelu, uzycie czatu, indeks RAG, baza i dysk (patrz diagnostics.py).
    Wynik jest trzymany ~15 s; refresh=1 (przycisk Odswiez) liczy od nowa."""
    response.headers.update(_NO_STORE)

    def compute() -> DiagnosticsResponse:
        now = clock()
        return collect_diagnostics(db, config, now, usage_day(now))

    return cache.get(compute, refresh=refresh)
