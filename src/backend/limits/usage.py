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

Gosc wersji testowej (guest/) ma GUEST_QUESTION_LIMIT pytan na cala sesje:
jego pytania i pliki ida na licznik dnia, w ktorym konto powstalo, wiec
polnoc ich nie odnawia. Do tego wszyscy goscie razem maja dzienny limit
GUEST_DAILY_TOTAL_LIMIT (wiersz guest_questions:<dzien> w usage_counters).
Ten wspolny licznik nie jest zwracany po bledzie modelu - nieudane wywolanie
tez kosztuje, a zwrot pozwalalby wywolywac model bez konca.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..guest.settings import GuestSettings
from ..llm.dates import warsaw_midnight, warsaw_now
from ..models import DailyAttachmentUsage, DailyUsage, UsageCounter, User, UserLimit, utcnow
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


class GuestQuestionsUnavailable(Exception):
    """Gosc nie moze juz pytac - API odpowiada 429 z kodem `code`."""

    code = "guest_unavailable"

    def __init__(self, limit: int, message: str) -> None:
        super().__init__(message)
        self.limit = limit
        self.message = message


class GuestLimitExceeded(GuestQuestionsUnavailable):
    """Gosc zuzyl GUEST_QUESTION_LIMIT pytan swojej sesji."""

    code = "guest_limit_reached"

    def __init__(self, limit: int) -> None:
        super().__init__(
            limit, f"Wykorzystano {limit} pytania wersji testowej. Zaloguj się kontem KSI, żeby pytać dalej."
        )


class GuestCapacityExceeded(GuestQuestionsUnavailable):
    """Goscie razem zuzyli dzisiejszy GUEST_DAILY_TOTAL_LIMIT."""

    code = "guest_capacity"

    def __init__(self, limit: int) -> None:
        super().__init__(
            limit, "Wersja testowa wyczerpała dziś swój limit pytań. Zaloguj się kontem KSI albo wróć jutro."
        )


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


# --- goscie wersji testowej --------------------------------------------------------------

GUEST_COUNTER_PREFIX = "guest_questions:"
# nowe sesje gosci z jednego adresu danego dnia: guest_ip:<dzien>:<HMAC adresu>
GUEST_ADDRESS_PREFIX = "guest_ip:"
# z HMAC (hex) zostaje 96 bitow - klucz usage_counters ma najwyzej 50 znakow
GUEST_ADDRESS_HASH_CHARS = 24


def guest_address_key(day: date, address_hash: str) -> str:
    """Licznik sesji gosci z jednego adresu (HMAC, nigdy sam adres) danego dnia."""
    return f"{GUEST_ADDRESS_PREFIX}{day.isoformat()}:{address_hash[:GUEST_ADDRESS_HASH_CHARS]}"


def guest_counter_key(day: date) -> str:
    """Wiersz usage_counters z liczba pytan wszystkich gosci danego dnia."""
    return f"{GUEST_COUNTER_PREFIX}{day.isoformat()}"


def guest_usage_day(user: User) -> date:
    """Dzien licznika goscia: dzien zalozenia konta - polnoc go nie odnawia."""
    return usage_day(user.created_at)


def _increment_counter(db: Session, key: str, limit: int) -> bool:
    stmt = (
        update(UsageCounter)
        .where(UsageCounter.key == key, UsageCounter.value < limit)
        .values(value=UsageCounter.value + 1)
        .execution_options(synchronize_session=False)
    )
    return bool(db.execute(stmt).rowcount)


def consume_counter(db: Session, key: str, limit: int) -> bool:
    """value + 1 w usage_counters, jesli miesci sie w limicie - atomowo, takze
    przy rownoleglych zapytaniach; commituje. False (po rollbacku) = limit
    wyczerpany."""
    try:
        consumed = _increment_counter(db, key, limit)
        if not consumed and db.get(UsageCounter, key) is None:
            try:
                with db.begin_nested():
                    db.execute(insert(UsageCounter).values(key=key, value=1))
                consumed = True
            except IntegrityError:
                consumed = _increment_counter(db, key, limit)
    except Exception:
        db.rollback()
        raise
    if not consumed:
        db.rollback()
        return False
    db.commit()
    return True


def consume_guest_question(db: Session, user: User, now: datetime, settings: GuestSettings) -> Reservation:
    """Zuzywa pytanie goscia: z limitu jego sesji i z dziennego limitu
    wszystkich gosci. Commituje.

    Raises:
        GuestLimitExceeded: gosc zuzyl swoje pytania.
        GuestCapacityExceeded: goscie zuzyli dzisiejszy limit (pytanie goscia
            wraca do jego puli).
    """
    day = guest_usage_day(user)
    if not _consume(db, DailyUsage, user.id, day, settings.question_limit):
        raise GuestLimitExceeded(settings.question_limit)
    if not consume_counter(db, guest_counter_key(usage_day(now)), settings.daily_total_limit):
        _refund(db, DailyUsage, Reservation(user_id=user.id, day=day))
        raise GuestCapacityExceeded(settings.daily_total_limit)
    return Reservation(user_id=user.id, day=day)


def guest_expires_at(user: User, settings: GuestSettings) -> datetime:
    """Kiedy konczy sie sesja goscia (i znika jego konto)."""
    created = user.created_at if user.created_at.tzinfo is not None else user.created_at.replace(tzinfo=timezone.utc)
    return created + timedelta(hours=settings.session_hours)


def guest_capacity_reached(db: Session, now: datetime, settings: GuestSettings) -> bool:
    """Czy goscie razem zuzyli juz dzisiejszy GUEST_DAILY_TOTAL_LIMIT."""
    row = db.get(UsageCounter, guest_counter_key(usage_day(now)), populate_existing=True)
    return row is not None and row.value >= settings.daily_total_limit


def consume_question_for(db: Session, user: User, now: datetime, guest: GuestSettings) -> Reservation:
    """Pytanie osoby: dzienny limit czlonka KSI albo limit goscia."""
    if user.is_guest:
        return consume_guest_question(db, user, now, guest)
    return consume_question(db, user.id, now)


def guest_questions_used(db: Session, user: User) -> int:
    """Ile pytan gosc juz zuzyl w swojej sesji."""
    return _used(db, user.id, guest_usage_day(user))


def ensure_guest_can_ask(db: Session, user: User, settings: GuestSettings) -> None:
    """Dla gosci: czy zostalo jakies pytanie (np. przed wyslaniem pliku).

    Raises:
        GuestLimitExceeded: gosc zuzyl swoje pytania.
    """
    if user.is_guest and guest_questions_used(db, user) >= settings.question_limit:
        raise GuestLimitExceeded(settings.question_limit)


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


def consume_attachment(
    db: Session, user_id: str, now: datetime, limit: int, day: date | None = None
) -> Reservation:
    """Zuzywa jedno miejsce z dziennego limitu wyslanych plikow i commituje.
    `day` = dzien licznika (gosc: dzien zalozenia konta), domyslnie dzisiaj.

    Raises:
        AttachmentLimitExceeded: limit na dzis wyczerpany.
    """
    day = day if day is not None else usage_day(now)
    if not _consume(db, DailyAttachmentUsage, user_id, day, limit):
        raise AttachmentLimitExceeded(
            limit, _used(db, user_id, day, DailyAttachmentUsage), next_reset(now), now
        )
    return Reservation(user_id=user_id, day=day)


def refund_attachment(db: Session, reservation: Reservation) -> None:
    """Oddaje miejsce po odrzuconym pliku. Nigdy ponizej 0."""
    _refund(db, DailyAttachmentUsage, reservation)


def attachments_used(db: Session, user_id: str, now: datetime, day: date | None = None) -> int:
    """Ile plikow osoba wyslala dzisiaj (doba wg czasu polskiego) albo
    danego dnia licznika (`day`, gosc)."""
    return _used(db, user_id, day if day is not None else usage_day(now), DailyAttachmentUsage)


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
    # dzienne liczniki gosci (pytania i sesje z adresu): klucz zaczyna sie od
    # daty ISO, wiec porownanie napisow wystarcza
    for prefix in (GUEST_COUNTER_PREFIX, GUEST_ADDRESS_PREFIX):
        result = db.execute(
            delete(UsageCounter).where(
                UsageCounter.key.startswith(prefix),
                UsageCounter.key < f"{prefix}{cutoff.isoformat()}",
            )
        )
        deleted += int(result.rowcount or 0)
    db.commit()
    return deleted
