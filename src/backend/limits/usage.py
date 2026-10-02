"""Dzienny limit pytan do modelu: zuzycie, zwrot, stan i wyjatki per osoba.

Doba konczy sie o polnocy czasu polskiego (Europe/Warsaw). Kazde pytanie,
ktore dochodzi do modelu (takze regeneracja i ponowienie), zuzywa jedno
pytanie PRZED wywolaniem modelu - atomowym UPDATE ... WHERE count < limit,
wiec rownolegle zapytania nie przekrocza limitu. Pytanie jest zwracane tylko
po bledzie po stronie serwera (blad modelu, pusta odpowiedz, nieudany zapis).
Rozlaczenie klienta (Stop, zamkniecie karty) w dowolnym momencie nie zwraca
pytania - model mogl juz zostac wywolany.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..llm.dates import warsaw_midnight, warsaw_now
from ..models import DailyUsage, UserLimit, utcnow
from .settings import get_daily_question_limit

logger = logging.getLogger(__name__)

# Dzienne liczniki sa potrzebne tylko do limitu i statystyk z ostatnich dni.
USAGE_RETENTION_DAYS = 90

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(timezone.utc)


def get_clock() -> Clock:
    """Dependency FastAPI: biezacy czas (testy podmieniaja zegar)."""
    return system_clock


class LimitExceeded(Exception):
    """Dzienny limit pytan wyczerpany - API odpowiada 429."""

    def __init__(self, limit: int, used: int, reset_at: datetime, checked_at: datetime) -> None:
        super().__init__(f"daily question limit {limit} reached")
        self.limit = limit
        self.used = used
        self.reset_at = reset_at
        # chwila sprawdzenia - od niej liczy sie Retry-After
        self.checked_at = checked_at


@dataclass(frozen=True)
class Reservation:
    """Zuzyte pytanie - zwrot trafia do tego samego dnia, nawet gdy
    odpowiedz skonczyla sie juz po polnocy."""
    user_id: str
    day: date


@dataclass(frozen=True)
class UsageStatus:
    used: int
    # None = bez limitu
    limit: int | None
    reset_at: datetime


@dataclass(frozen=True)
class UserOverride:
    # None = bez limitu
    daily_limit: int | None
    note: str | None
    updated_at: datetime


def usage_day(now: datetime) -> date:
    """Dzien rozliczeniowy chwili `now` (data w czasie polskim)."""
    return warsaw_now(now).date()


def next_reset(now: datetime) -> datetime:
    """Najblizsza polnoc czasu polskiego po `now` (w UTC)."""
    return warsaw_midnight(usage_day(now) + timedelta(days=1)).astimezone(timezone.utc)


def get_override(db: Session, user_id: str) -> UserLimit | None:
    return db.get(UserLimit, user_id, populate_existing=True)


def effective_limit(db: Session, user_id: str) -> int | None:
    """Limit osoby: wyjatek (None = bez limitu), a bez wyjatku limit globalny."""
    override = get_override(db, user_id)
    if override is not None:
        return override.daily_limit
    return get_daily_question_limit(db)


def _used(db: Session, user_id: str, day: date) -> int:
    stmt = select(DailyUsage.count).where(DailyUsage.user_id == user_id, DailyUsage.day == day)
    return int(db.execute(stmt).scalar_one_or_none() or 0)


def _increment(db: Session, user_id: str, day: date, limit: int | None) -> bool:
    """count + 1, jesli miesci sie w limicie. Atomowo w bazie: warunek
    count < limit jest sprawdzany w tym samym UPDATE."""
    stmt = (
        update(DailyUsage)
        .where(DailyUsage.user_id == user_id, DailyUsage.day == day)
        .values(count=DailyUsage.count + 1)
        .execution_options(synchronize_session=False)
    )
    if limit is not None:
        stmt = stmt.where(DailyUsage.count < limit)
    return bool(db.execute(stmt).rowcount)


def _row_exists(db: Session, user_id: str, day: date) -> bool:
    stmt = select(DailyUsage.user_id).where(DailyUsage.user_id == user_id, DailyUsage.day == day)
    return db.execute(stmt).first() is not None


def _try_consume(db: Session, user_id: str, day: date, limit: int | None) -> bool:
    if _increment(db, user_id, day, limit):
        return True
    if _row_exists(db, user_id, day):
        return False
    if limit is not None and limit <= 0:
        return False
    # pierwsze pytanie danego dnia; rownolegle wstawienie konczy sie na kluczu
    # glownym - wtedy wiersz juz jest i wystarczy go zwiekszyc
    try:
        with db.begin_nested():
            db.execute(insert(DailyUsage).values(user_id=user_id, day=day, count=1))
        return True
    except IntegrityError:
        return _increment(db, user_id, day, limit)


def consume_question(db: Session, user_id: str, now: datetime) -> Reservation:
    """Zuzywa jedno pytanie z dziennego limitu osoby i commituje.

    Raises:
        LimitExceeded: limit na dzis wyczerpany (nic nie zostalo zuzyte).
    """
    day = usage_day(now)
    limit = effective_limit(db, user_id)
    try:
        consumed = _try_consume(db, user_id, day, limit)
    except Exception:
        db.rollback()
        raise
    if not consumed:
        db.rollback()
        if limit is None:
            # bez limitu UPDATE/INSERT zawsze sie udaje - tu nie powinno dojsc
            raise RuntimeError(f"usage counter of user {user_id} could not be incremented")
        raise LimitExceeded(limit, _used(db, user_id, day), next_reset(now), now)
    db.commit()
    return Reservation(user_id=user_id, day=day)


def refund_question(db: Session, reservation: Reservation) -> None:
    """Oddaje zuzyte pytanie (blad serwera, nic nie zapisano). Nigdy ponizej 0."""
    db.execute(
        update(DailyUsage)
        .where(
            DailyUsage.user_id == reservation.user_id,
            DailyUsage.day == reservation.day,
            DailyUsage.count > 0,
        )
        .values(count=DailyUsage.count - 1)
        .execution_options(synchronize_session=False)
    )
    db.commit()


def refund_in_new_session(session_factory: Callable[[], Session], reservation: Reservation) -> None:
    """refund_question we wlasnej sesji; blad jest logowany, nie przerywa tury
    (najwyzej osoba straci jedno pytanie do polnocy)."""
    db = session_factory()
    try:
        refund_question(db, reservation)
    except Exception:
        db.rollback()
        logger.exception("refunding question failed (user %s)", reservation.user_id)
    finally:
        db.close()


def usage_status(db: Session, user_id: str, now: datetime) -> UsageStatus:
    """Zuzycie osoby dzisiaj, jej limit i chwila odnowienia."""
    return UsageStatus(
        used=_used(db, user_id, usage_day(now)),
        limit=effective_limit(db, user_id),
        reset_at=next_reset(now),
    )


# --- wyjatki per osoba (panel administratora) --------------------------------------------

def set_user_limit(
    db: Session, user_id: str, *, daily_limit: int | None, note: str | None, admin_id: str | None
) -> UserLimit:
    """Ustawia albo zmienia wyjatek osoby (daily_limit None = bez limitu)."""
    row = get_override(db, user_id)
    if row is None:
        row = UserLimit(user_id=user_id)
        db.add(row)
    row.daily_limit = daily_limit
    row.note = note
    row.updated_by = admin_id
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def clear_user_limit(db: Session, user_id: str) -> bool:
    """Usuwa wyjatek osoby; False = nie bylo wyjatku."""
    result = db.execute(delete(UserLimit).where(UserLimit.user_id == user_id))
    db.commit()
    return bool(result.rowcount)


# --- sprzatanie -----------------------------------------------------------------------------------

def purge_old_usage(db: Session, retention_days: int = USAGE_RETENTION_DAYS, now: datetime | None = None) -> int:
    """Kasuje dzienne liczniki starsze niz retention_days."""
    cutoff = usage_day(now if now is not None else system_clock()) - timedelta(days=retention_days)
    result = db.execute(delete(DailyUsage).where(DailyUsage.day < cutoff))
    db.commit()
    return int(result.rowcount or 0)
