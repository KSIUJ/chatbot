"""Blokada czatu po ostrzezeniach za proby obejscia promptu systemowego.

Ostrzezenie = incydent, w ktorym model dal znacznik [[NARUSZENIE]] (source
"model" albo "both") - tylko wtedy osoba dostaje w odpowiedzi informacje, ze
proba zostala odnotowana. Sama heurystyka ostrzezeniem nie jest: osoba nic
nie widzi, a heurystyka miewa falszywe alarmy. Nie licza sie incydenty
odrzucone przez zarzad (dismissed) ani sprzed zdjecia blokady
(users.warnings_reset_at). Incydenty znikaja po INCIDENT_RETENTION_DAYS,
wiec stare ostrzezenia wygasaja same; blokade zdejmuje tylko zarzad.

Po WARNING_LIMIT ostrzezeniach osoba nie moze zadawac pytan ani wysylac
plikow (403 chat_blocked) i dostaje prosbe o kontakt z zarzadem KSI.
Historia rozmow zostaje dostepna.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import SecurityIncident, User, utcnow

logger = logging.getLogger(__name__)

WARNING_LIMIT = 3
CHAT_BLOCKED = "chat_blocked"
BLOCKED_MESSAGE = (
    f"Twój dostęp do czatu został zablokowany po {WARNING_LIMIT} ostrzeżeniach o próbach obejścia "
    "zasad. Skontaktuj się z członkiem zarządu KSI, aby wyjaśnić sytuację."
)


class ChatBlocked(Exception):
    """Osoba zablokowana po ostrzezeniach - API odpowiada 403 chat_blocked."""

    def __init__(self) -> None:
        super().__init__("chat blocked after warnings")


class BlockedUserNotFound(LookupError):
    """Brak konta o tym id - API odpowiada 404."""


@dataclass(frozen=True)
class WarnedUser:
    """Osoba z ostrzezeniami albo blokada (lista dla zarzadu)."""
    user: User
    warnings: int
    last_warning_at: datetime | None


def _counts_as_warning() -> ColumnElement[bool]:
    """Warunek "incydent jest ostrzezeniem" (wymaga zlaczenia z User)."""
    return and_(
        SecurityIncident.user_id == User.id,
        SecurityIncident.source.in_(("model", "both")),
        SecurityIncident.status != "dismissed",
        or_(User.warnings_reset_at.is_(None), SecurityIncident.created_at > User.warnings_reset_at),
    )


def count_warnings(db: Session, user_id: str) -> int:
    stmt = select(func.count()).select_from(SecurityIncident).join(User, _counts_as_warning()).where(User.id == user_id)
    return int(db.execute(stmt).scalar_one())


def apply_warning_block(db: Session, user_id: str) -> bool:
    """Blokuje osobe, ktora ma co najmniej WARNING_LIMIT ostrzezen. Wolane po
    zapisaniu incydentu; True = blokada zalozona teraz."""
    user = db.get(User, user_id, populate_existing=True)
    if user is None or user.chat_blocked_at is not None:
        return False
    warnings = count_warnings(db, user_id)
    if warnings < WARNING_LIMIT:
        return False
    user.chat_blocked_at = utcnow()
    db.commit()
    logger.warning("chat blocked for user %s after %d warnings", user_id, warnings)
    return True


def ensure_not_blocked(user: User) -> None:
    """Krok /chat, /chat/stream i wysylania pliku - przed limitem i modelem.

    Raises:
        ChatBlocked: osoba zablokowana po ostrzezeniach.
    """
    if user.chat_blocked_at is not None:
        raise ChatBlocked()


def is_blocked(user: User) -> bool:
    return user.chat_blocked_at is not None


def chat_blocked_response() -> JSONResponse:
    """403 z kodem chat_blocked i prosba o kontakt z zarzadem."""
    return JSONResponse(
        status_code=403,
        content={"detail": {"code": CHAT_BLOCKED, "message": BLOCKED_MESSAGE, "warning_limit": WARNING_LIMIT}},
        headers={"Cache-Control": "no-store"},
    )


async def chat_blocked_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handler wyjatku ChatBlocked dla calej aplikacji."""
    if not isinstance(exc, ChatBlocked):
        raise exc
    return chat_blocked_response()


# --- zarzad ---------------------------------------------------------------------------

def list_warned_users(db: Session) -> list[WarnedUser]:
    """Zablokowani (od najdawniej zablokowanych), a za nimi osoby z
    ostrzezeniami (od najwiekszej liczby)."""
    warnings = (
        select(
            SecurityIncident.user_id.label("user_id"),
            func.count().label("warnings"),
            func.max(SecurityIncident.created_at).label("last_warning_at"),
        )
        .join(User, _counts_as_warning())
        .group_by(SecurityIncident.user_id)
        .subquery()
    )
    count = func.coalesce(warnings.c.warnings, 0)
    stmt = (
        select(User, count, warnings.c.last_warning_at)
        .outerjoin(warnings, warnings.c.user_id == User.id)
        .where(or_(User.chat_blocked_at.is_not(None), count > 0))
        .order_by(User.chat_blocked_at.is_(None), User.chat_blocked_at, count.desc(), User.id)
    )
    return [WarnedUser(user, int(n), last) for user, n, last in db.execute(stmt)]


def warned_user(db: Session, user: User) -> WarnedUser:
    stmt = (
        select(func.max(SecurityIncident.created_at))
        .select_from(SecurityIncident)
        .join(User, _counts_as_warning())
        .where(User.id == user.id)
    )
    return WarnedUser(user, count_warnings(db, user.id), db.execute(stmt).scalar_one_or_none())


def unblock_user(db: Session, user_id: str, admin_id: str) -> WarnedUser:
    """Zdejmuje blokade i zeruje ostrzezenia (licza sie tylko nowe incydenty).

    Raises:
        BlockedUserNotFound: brak konta o tym id.
    """
    user = db.get(User, user_id, populate_existing=True)
    if user is None:
        raise BlockedUserNotFound(user_id)
    was_blocked = user.chat_blocked_at is not None
    user.chat_blocked_at = None
    user.warnings_reset_at = utcnow()
    db.commit()
    db.refresh(user)
    logger.info("warnings reset for user %s by admin %s (was blocked: %s)", user_id, admin_id, was_blocked)
    return warned_user(db, user)
