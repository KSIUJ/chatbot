"""Odstep miedzy zapytaniami i ponowienia (pipeline/scrapers/common/throttle.py)."""

from __future__ import annotations

import pytest

from pipeline.scrapers.common.throttle import MAX_BACKOFF, Throttle, backoff_seconds


def test_throttle_waits_only_for_the_rest_of_delay():
    times = iter([0.0, 0.25, 0.25, 5.0, 5.0])
    sleeps: list[float] = []
    throttle = Throttle(1.0, sleeps.append, lambda: next(times))

    throttle.wait()  # pierwsze zapytanie bez czekania
    throttle.wait()  # 0.25 s po poprzednim - czeka reszte
    throttle.wait()  # dawno po poprzednim - bez czekania

    assert sleeps == [pytest.approx(0.75)]


@pytest.mark.parametrize(
    ("attempt", "retry_after", "expected"),
    [
        (0, None, 2.0),
        (1, None, 4.0),
        (2, "", 8.0),
        (0, "30", 30.0),
        # Retry-After krotszy niz backoff - backoff
        (2, "1", 8.0),
        # data HTTP albo smieci - ignorowane
        (0, "Wed, 21 Oct 2026 07:28:00 GMT", 2.0),
        (0, "²", 2.0),
        # nie dluzej niz 300 s
        (0, "86400", MAX_BACKOFF),
        (20, None, MAX_BACKOFF),
    ],
)
def test_backoff_seconds(attempt, retry_after, expected):
    assert backoff_seconds(attempt, retry_after) == expected


def test_backoff_custom_cap():
    assert backoff_seconds(0, "100", cap=60.0) == 60.0
