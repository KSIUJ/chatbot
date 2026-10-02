"""
Dzienny limit pytan (serwis limits/usage.py): doba konczy sie o polnocy czasu
polskiego, zwrot przy nieudanym pytaniu, wyjatki per osoba (wlasny limit,
bez limitu, zablokowany), atomowe zuzycie przy rownoleglych zapytaniach
i sprzatanie starych wierszy.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.backend.limits.settings import LimitSettings, load_default_limits, save_limit_settings
from src.backend.limits.usage import (
    LimitExceeded,
    USAGE_RETENTION_DAYS,
    clear_user_limit,
    consume_question,
    effective_limit,
    next_reset,
    purge_old_usage,
    refund_question,
    set_user_limit,
    usage_day,
    usage_status,
)
from src.backend.models import DailyUsage, User

# 2 pazdziernika 2026 (CEST, UTC+2): polnoc w Krakowie = 22:00 UTC poprzedniego dnia
MORNING = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user_id(db) -> str:
    user = User(oidc_sub="limits-user", email="u@student.uj.edu.pl", name="Ula")
    db.add(user)
    db.commit()
    return user.id


def _set_global_limit(db, limit: int) -> None:
    defaults = load_default_limits({})
    save_limit_settings(db, LimitSettings(daily_question_limit=limit, attachments=defaults.attachments), None)


# --- doba wg czasu polskiego --------------------------------------------------------------

def test_day_switches_at_warsaw_midnight_in_summer_time():
    before = datetime(2026, 10, 2, 21, 59, 59, tzinfo=timezone.utc)
    after = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)

    assert usage_day(before) == date(2026, 10, 2)
    assert usage_day(after) == date(2026, 10, 3)
    assert next_reset(before) == after


def test_day_switches_at_warsaw_midnight_in_winter_time():
    before = datetime(2026, 12, 1, 22, 59, tzinfo=timezone.utc)
    after = datetime(2026, 12, 1, 23, 0, tzinfo=timezone.utc)

    assert usage_day(before) == date(2026, 12, 1)
    assert usage_day(after) == date(2026, 12, 2)
    assert next_reset(before) == after


def test_reset_on_the_day_clocks_go_back_is_midnight_cet():
    # 25 pazdziernika 2026 zmiana czasu - nastepna polnoc juz w CET (UTC+1)
    moment = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

    assert next_reset(moment) == datetime(2026, 10, 25, 23, 0, tzinfo=timezone.utc)


# --- zuzycie i zwrot -----------------------------------------------------------------------

def test_consume_counts_up_to_the_limit_then_raises(db, user_id):
    _set_global_limit(db, 3)

    for _ in range(3):
        consume_question(db, user_id, MORNING)

    with pytest.raises(LimitExceeded) as exc_info:
        consume_question(db, user_id, MORNING)
    assert exc_info.value.limit == 3
    assert exc_info.value.reset_at == datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)
    status = usage_status(db, user_id, MORNING)
    assert (status.used, status.limit) == (3, 3)


def test_refund_gives_the_question_back(db, user_id):
    _set_global_limit(db, 1)
    reservation = consume_question(db, user_id, MORNING)

    refund_question(db, reservation)

    assert usage_status(db, user_id, MORNING).used == 0
    consume_question(db, user_id, MORNING)


def test_refund_goes_to_the_day_of_the_reservation(db, user_id):
    _set_global_limit(db, 5)
    reservation = consume_question(db, user_id, datetime(2026, 10, 2, 21, 59, tzinfo=timezone.utc))
    consume_question(db, user_id, datetime(2026, 10, 2, 22, 1, tzinfo=timezone.utc))

    refund_question(db, reservation)

    assert usage_status(db, user_id, datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)).used == 0
    assert usage_status(db, user_id, datetime(2026, 10, 2, 23, 0, tzinfo=timezone.utc)).used == 1


def test_refund_never_goes_below_zero(db, user_id):
    reservation = consume_question(db, user_id, MORNING)
    refund_question(db, reservation)
    refund_question(db, reservation)

    assert usage_status(db, user_id, MORNING).used == 0


def test_limit_resets_at_warsaw_midnight(db, user_id):
    _set_global_limit(db, 1)
    consume_question(db, user_id, datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc))
    with pytest.raises(LimitExceeded):
        consume_question(db, user_id, datetime(2026, 10, 2, 21, 59, tzinfo=timezone.utc))

    consume_question(db, user_id, datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc))


def test_default_global_limit_is_ten(db, user_id):
    assert load_default_limits({}).daily_question_limit == 10
    assert effective_limit(db, user_id) == 10


# --- wyjatki per osoba ---------------------------------------------------------------------

def test_override_with_custom_limit(db, user_id):
    _set_global_limit(db, 1)
    set_user_limit(db, user_id, daily_limit=3, note="projekt", admin_id=None)

    for _ in range(3):
        consume_question(db, user_id, MORNING)
    with pytest.raises(LimitExceeded) as exc_info:
        consume_question(db, user_id, MORNING)
    assert exc_info.value.limit == 3


def test_unlimited_override_still_counts_usage(db, user_id):
    _set_global_limit(db, 1)
    set_user_limit(db, user_id, daily_limit=None, note=None, admin_id=None)

    for _ in range(5):
        consume_question(db, user_id, MORNING)

    status = usage_status(db, user_id, MORNING)
    assert (status.used, status.limit) == (5, None)


def test_zero_override_blocks_the_user(db, user_id):
    set_user_limit(db, user_id, daily_limit=0, note="naduzycia", admin_id=None)

    with pytest.raises(LimitExceeded):
        consume_question(db, user_id, MORNING)
    assert usage_status(db, user_id, MORNING).used == 0


def test_clearing_override_restores_global_limit(db, user_id):
    _set_global_limit(db, 2)
    set_user_limit(db, user_id, daily_limit=None, note=None, admin_id=None)

    assert clear_user_limit(db, user_id) is True
    assert clear_user_limit(db, user_id) is False
    assert effective_limit(db, user_id) == 2


# --- rownoleglosc -----------------------------------------------------------------------------

def test_parallel_consumers_never_exceed_the_limit(session_factory, user_id):
    db = session_factory()
    _set_global_limit(db, 5)
    db.close()
    results: list[bool] = []
    lock = threading.Lock()
    start = threading.Barrier(12)

    def worker() -> None:
        session = session_factory()
        try:
            start.wait()
            try:
                consume_question(session, user_id, MORNING)
                ok = True
            except LimitExceeded:
                ok = False
            with lock:
                results.append(ok)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 5
    db = session_factory()
    try:
        assert usage_status(db, user_id, MORNING).used == 5
    finally:
        db.close()


# --- sprzatanie -----------------------------------------------------------------------------------

def test_purge_removes_rows_older_than_retention(db, user_id):
    today = usage_day(MORNING)
    old = today - timedelta(days=USAGE_RETENTION_DAYS + 1)
    recent = today - timedelta(days=USAGE_RETENTION_DAYS - 1)
    db.add_all([
        DailyUsage(user_id=user_id, day=old, count=3),
        DailyUsage(user_id=user_id, day=recent, count=2),
    ])
    db.commit()

    assert purge_old_usage(db, now=MORNING) == 1
    assert list(db.execute(select(DailyUsage.day)).scalars()) == [recent]
