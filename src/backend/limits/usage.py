"""Dzienny limit pytan do modelu: zuzycie, zwrot, stan i wyjatki per osoba.

Doba konczy sie o polnocy czasu polskiego (Europe/Warsaw). Kazde pytanie,
ktore dochodzi do modelu (takze regeneracja i ponowienie), zuzywa jedno
pytanie PRZED wywolaniem modelu - atomowym UPDATE ... WHERE count < limit,
wiec rownolegle zapytania nie przekrocza limitu. Pytanie jest zwracane tylko
po bledzie po stronie serwera (blad modelu, pusta odpowiedz, nieudany zapis).
Rozlaczenie klienta (Stop, zamkniecie karty) w dowolnym momencie nie zwraca
pytania - model mogl juz zostac wywolany.

Ten sam licznik (osobna tabela daily_attachment_usage) liczy wyslane pliki
dla limitu attachments.max_per_day: plik zuzywa jedno miejsce przed zapisem
na dysk, a odrzucony (typ, rozmiar, nieczytelny) je oddaje.
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
from ..models import DailyAttachmentUsage, DailyUsage, UserLimit, utcnow
from .settings import get_daily_question_limit

logger = logging.getLogger(__name__)

# Dzienne liczniki sa potrzebne tylko do limitu i statystyk z ostatnich dni.
USAGE_RETENTION_DAYS = 90

Clock = Callable[[], datetime]
# tabela dziennego licznika: pytania albo wyslane pliki (te same kolumny)
CounterTable = type[DailyUsage] | type[DailyAttachmentUsage]


def system_clock() -> datetime:
    return datetime.now(timezone.utc)


def get_clock() -> Clock:
    """Dependency FastAPI: biezacy czas (testy podmieniaja zegar)."""
    return system_clock


class LimitExceeded(Exception):
    """Dzienny limit pytan wyczerpany - API odpowiada 429."""

    def __init__(self, limit: int, used: int, reset_at: datetime, checked_at: datetime) -> None:
        super().__init__(f"daily limit {limit} reached")
        self.limit = limit
        self.used = used
        self.reset_at = reset_at
        # chwila sprawdzenia - od niej liczy sie Retry-After
        self.checked_at = checked_at


class AttachmentLimitExceeded(LimitExceeded):
    """Dzienny limit wyslanych plikow wyczerpany - API odpowiada 429
    attachments_limited (osobny handler, nie rate_limited)."""


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


def _used(db: Session, user_id: str, day: date, table: CounterTable = DailyUsage) -> int:
    stmt = select(table.count).where(table.user_id == user_id, table.day == day)
    return int(db.execute(stmt).scalar_one_or_none() or 0)


def _increment(db: Session, table: CounterTable, user_id: str, day: date, limit: int | None) -> bool:
    """count + 1, jesli miesci sie w limicie. Atomowo w bazie: warunek
    count < limit jest sprawdzany w tym samym UPDATE."""
    stmt = (
        update(table)
        .where(table.user_id == user_id, table.day == day)
        .values(count=table.count + 1)
        .execution_options(synchronize_session=False)
    )
    if limit is not None:
        stmt = stmt.where(table.count < limit)
    return bool(db.execute(stmt).rowcount)


def _row_exists(db: Session, table: CounterTable, user_id: str, day: date) -> bool:
    stmt = select(table.user_id).where(table.user_id == user_id, table.day == day)
    return db.execute(stmt).first() is not None


def _try_consume(db: Session, table: CounterTable, user_id: str, day: date, limit: int | None) -> bool:
    if _increment(db, table, user_id, day, limit):
        return True
    if _row_exists(db, table, user_id, day):
        return False
    if limit is not None and limit <= 0:
        return False
    # pierwsze uzycie danego dnia; rownolegle wstawienie konczy sie na kluczu
    # glownym - wtedy wiersz juz jest i wystarczy go zwiekszyc
    try:
        with db.begin_nested():
            db.execute(insert(table).values(user_id=user_id, day=day, count=1))
        return True
    except IntegrityError:
        return _increment(db, table, user_id, day, limit)


def _consume(db: Session, table: CounterTable, user_id: str, day: date, limit: int | None) -> bool:
    """Zuzywa jedno miejsce i commituje; False (po rollbacku) = limit wyczerpany."""
    try:
        consumed = _try_consume(db, table, user_id, day, limit)
    except Exception:
        db.rollback()
        raise
    if not consumed:
        db.rollback()
        return False
    db.commit()
    return True


def _refund(db: Session, table: CounterTable, reservation: Reservation) -> None:
    """Oddaje zuzyte miejsce i commituje. Nigdy ponizej 0."""
    db.execute(
        update(table)
        .where(
            table.user_id == reservation.user_id,
            table.day == reservation.day,
            table.count > 0,
        )
        .values(count=table.count - 1)
        .execution_options(synchronize_session=False)
    )
    db.commit()


def consume_question(db: Session, user_id: str, now: datetime) -> Reservation:
    """Zuzywa jedno pytanie z dziennego limitu osoby i commituje.

    Raises:
        LimitExceeded: limit na dzis wyczerpany (nic nie zostalo zuzyte).
    """
    day = usage_day(now)
    limit = effective_limit(db, user_id)
    if not _consume(db, DailyUsage, user_id, day, limit):
        if limit is None:
            # bez limitu UPDATE/INSERT zawsze sie udaje - tu nie powinno dojsc
            raise RuntimeError(f"usage counter of user {user_id} could not be incremented")
        raise LimitExceeded(limit, _used(db, user_id, day), next_reset(now), now)
    return Reservation(user_id=user_id, day=day)


def refund_question(db: Session, reservation: Reservation) -> None:
    """Oddaje zuzyte pytanie (blad serwera, nic nie zapisano). Nigdy ponizej 0."""
    _refund(db, DailyUsage, reservation)


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


def consume_attachment(db: Session, user_id: str, now: datetime, limit: int) -> Reservation:
    """Zuzywa jedno miejsce z dziennego limitu wyslanych plikow i commituje.

    Raises:
        AttachmentLimitExceeded: limit na dzis wyczerpany.
    """
    day = usage_day(now)
    if not _consume(db, DailyAttachmentUsage, user_id, day, limit):
        raise AttachmentLimitExceeded(
            limit, _used(db, user_id, day, DailyAttachmentUsage), next_reset(now), now
        )
    return Reservation(user_id=user_id, day=day)


def refund_attachment(db: Session, reservation: Reservation) -> None:
    """Oddaje miejsce po odrzuconym pliku. Nigdy ponizej 0."""
    _refund(db, DailyAttachmentUsage, reservation)


def attachments_used(db: Session, user_id: str, now: datetime) -> int:
    """Ile plikow osoba wyslala dzisiaj (doba wg czasu polskiego)."""
    return _used(db, user_id, usage_day(now), DailyAttachmentUsage)


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
    """Kasuje dzienne liczniki (pytan i plikow) starsze niz retention_days."""
    cutoff = usage_day(now if now is not None else system_clock()) - timedelta(days=retention_days)
    deleted = 0
    for table in (DailyUsage, DailyAttachmentUsage):
        result = db.execute(delete(table).where(table.day < cutoff))
        deleted += int(result.rowcount or 0)
    db.commit()
    return deleted
