"""Data do promptu systemowego: czas w Krakowie (Europe/Warsaw), polska data
slownie i rok akademicki. Bez locale - nazwy miesiecy i dni sa tu wprost."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WARSAW_TZ_NAME = "Europe/Warsaw"

# dopelniacz: "2 pazdziernika"
_MONTHS_GENITIVE = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
)
# date.weekday(): 0 = poniedzialek
_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")

# rok akademicki zaczyna sie 1 pazdziernika
ACADEMIC_YEAR_START_MONTH = 10

_CET = timedelta(hours=1)
_CEST = timedelta(hours=2)
# zmiana czasu w UE: ostatnia niedziela marca i pazdziernika o 01:00 UTC
_DST_SWITCH_HOUR_UTC = 1


@lru_cache(maxsize=1)
def _warsaw_zone() -> tzinfo | None:
    """Strefa z bazy IANA (pakiet tzdata z requirements.txt); None tylko gdy
    bazy brak mimo to - wtedy warsaw_now liczy czas wg regul UE."""
    try:
        return ZoneInfo(WARSAW_TZ_NAME)
    except ZoneInfoNotFoundError:
        return None


def _last_sunday(year: int, month: int) -> date:
    first_of_next = date(year + month // 12, month % 12 + 1, 1)
    last_day = first_of_next - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - 6) % 7)


def eu_warsaw_offset(moment: datetime) -> timedelta:
    """Przesuniecie czasu polskiego wg regul UE (CET/CEST) dla chwili w UTC.
    Zapas na wypadek braku bazy stref czasowych."""
    utc = moment.astimezone(timezone.utc)
    year = utc.year
    dst_start = datetime.combine(_last_sunday(year, 3), datetime.min.time(), timezone.utc)
    dst_end = datetime.combine(_last_sunday(year, 10), datetime.min.time(), timezone.utc)
    switch = timedelta(hours=_DST_SWITCH_HOUR_UTC)
    return _CEST if dst_start + switch <= utc < dst_end + switch else _CET


def warsaw_now(moment: datetime) -> datetime:
    """Chwila `moment` w czasie polskim. Naiwny datetime traktujemy jako UTC."""
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    zone = _warsaw_zone()
    if zone is not None:
        return aware.astimezone(zone)
    return aware.astimezone(timezone(eu_warsaw_offset(aware)))


def polish_date(day: date) -> str:
    """Np. "2 października 2026 (piątek)"."""
    return f"{day.day} {_MONTHS_GENITIVE[day.month - 1]} {day.year} ({_WEEKDAYS[day.weekday()]})"


def academic_year(day: date) -> str:
    """Rok akademicki dnia `day`, np. "2026/2027" (30 wrzesnia nalezy do poprzedniego)."""
    start = day.year if day.month >= ACADEMIC_YEAR_START_MONTH else day.year - 1
    return f"{start}/{start + 1}"
