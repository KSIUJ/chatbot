"""Endpoint stanu dziennego limitu i odpowiedz 429 po jego wyczerpaniu.

Za nginxem jest pod /api/* (nginx obcina /api).

    GET /usage -> {used, limit (null = bez limitu), reset_at, chat_enabled,
                   chat_disabled_message, chat_blocked, attachments: {limity plikow,
                   used_today, images_supported}, guest}

Gosc wersji testowej dostaje pytania i pliki calej sesji (guest=true), a po
ich wyczerpaniu 429 guest_limit_reached / guest_capacity.
"""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..auth.dependencies import require_member
from ..database import get_db
from ..guest.settings import GUEST_MAX_FILE_MB, GuestSettings, get_guest_settings
from ..llm.provider import provider_supports_images
from ..models import User
from ..security.blocks import is_blocked
from .schemas import AttachmentUsage, UsageResponse
from .settings import MAX_IMAGE_MB, ChatDisabled, get_attachment_limits, get_chat_availability
from .usage import (
    Clock,
    GuestQuestionsUnavailable,
    LimitExceeded,
    UsageStatus,
    attachments_used,
    get_clock,
    guest_capacity_reached,
    guest_expires_at,
    guest_questions_used,
    guest_usage_day,
    usage_status,
)

RATE_LIMITED = "rate_limited"
CHAT_DISABLED = "chat_disabled"

router = APIRouter(tags=["limits"])


@router.get("/usage", response_model=UsageResponse)
def get_usage(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
    clock: Clock = Depends(get_clock),
    guest: GuestSettings = Depends(get_guest_settings),
) -> UsageResponse:
    """Dzienny limit pytan biezacego uzytkownika (podpowiedz w sidebarze) i stan
    wylacznika czatu i blokady osoby (baner nad polem pytania). Gosc dostaje
    limit swojej sesji i jej koniec."""
    response.headers["Cache-Control"] = "no-store"
    now = clock()
    availability = get_chat_availability(db)
    attachments = get_attachment_limits(db)
    if user.is_guest:
        status = UsageStatus(
            used=guest_questions_used(db, user),
            limit=guest.question_limit,
            reset_at=guest_expires_at(user, guest),
        )
        max_files = min(attachments.max_per_day, guest.attachment_limit)
        files_used = attachments_used(db, user.id, now, day=guest_usage_day(user))
        max_file_mb = min(attachments.max_file_mb, GUEST_MAX_FILE_MB)
        capacity_reached = guest_capacity_reached(db, now, guest)
    else:
        status = usage_status(db, user.id, now)
        max_files = attachments.max_per_day
        files_used = attachments_used(db, user.id, now)
        max_file_mb = attachments.max_file_mb
        capacity_reached = False
    return UsageResponse(
        used=status.used,
        limit=status.limit,
        reset_at=status.reset_at,
        chat_enabled=availability.enabled,
        chat_disabled_message=availability.message,
        chat_blocked=is_blocked(user),
        attachments=AttachmentUsage(
            max_file_mb=max_file_mb,
            max_image_mb=min(MAX_IMAGE_MB, max_file_mb),
            max_files_per_message=attachments.max_files_per_message,
            max_per_day=max_files,
            used_today=files_used,
            allowed_types=list(attachments.allowed_types),
            images_supported=provider_supports_images(),
        ),
        guest=user.is_guest,
        guest_capacity_reached=capacity_reached,
    )


def rate_limited_response(exc: LimitExceeded) -> JSONResponse:
    """429 z kodem rate_limited, limitem i chwila odnowienia; Retry-After w
    sekundach do polnocy czasu polskiego (co najmniej 1)."""
    seconds = (exc.reset_at - exc.checked_at).total_seconds()
    retry_after = max(1, math.ceil(seconds))
    return JSONResponse(
        status_code=429,
        content={
            "detail": {
                "code": RATE_LIMITED,
                "message": f"Wykorzystano dzienny limit pytań ({exc.limit}). Limit odnowi się o północy.",
                "limit": exc.limit,
                "reset_at": exc.reset_at.isoformat(),
            }
        },
        headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
    )


def chat_disabled_response(exc: ChatDisabled) -> JSONResponse:
    """503 z kodem chat_disabled; admin_message = komunikat zarzadu albo null
    (frontend pokazuje wtedy przetlumaczony tekst domyslny)."""
    return JSONResponse(
        status_code=503,
        content={"detail": {"code": CHAT_DISABLED, "message": exc.message, "admin_message": exc.admin_message}},
        headers={"Cache-Control": "no-store"},
    )


async def chat_disabled_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handler wyjatku ChatDisabled dla /chat i /chat/stream."""
    if not isinstance(exc, ChatDisabled):
        raise exc
    return chat_disabled_response(exc)


def guest_unavailable_response(exc: GuestQuestionsUnavailable) -> JSONResponse:
    """429 gosci: guest_limit_reached (pytania sesji) albo guest_capacity
    (dzienny limit wszystkich gosci); bez Retry-After - pomaga tylko logowanie."""
    return JSONResponse(
        status_code=429,
        content={"detail": {"code": exc.code, "message": exc.message, "limit": exc.limit}},
        headers={"Cache-Control": "no-store"},
    )


async def guest_unavailable_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handler wyjatkow GuestQuestionsUnavailable (/chat, /chat/stream, /attachments)."""
    if not isinstance(exc, GuestQuestionsUnavailable):
        raise exc
    return guest_unavailable_response(exc)


async def limit_exceeded_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handler wyjatku LimitExceeded dla calej aplikacji (/chat i /chat/stream)."""
    if not isinstance(exc, LimitExceeded):
        raise exc
    return rate_limited_response(exc)
