"""Ustawienia wersji testowej bez konta (GUEST_*) z env."""

from __future__ import annotations

import pytest

from src.backend.guest.settings import GuestConfigError, load_guest_settings


def test_defaults():
    settings = load_guest_settings({})

    assert settings.enabled is True
    assert settings.question_limit == 2
    assert settings.session_hours == 24
    assert settings.sessions_per_ip_per_day == 5
    assert settings.daily_total_limit == 300
    assert settings.attachment_limit == 4


@pytest.mark.parametrize("value", ["off", "false", "0", "nie", " OFF "])
def test_guest_mode_can_be_switched_off(value):
    assert load_guest_settings({"GUEST_MODE": value}).enabled is False


def test_values_from_env():
    settings = load_guest_settings({
        "GUEST_QUESTION_LIMIT": "3",
        "GUEST_SESSION_HOURS": "12",
        "GUEST_SESSIONS_PER_IP_PER_DAY": "10",
        "GUEST_DAILY_TOTAL_LIMIT": "50",
        "GUEST_ATTACHMENT_LIMIT": "0",
    })

    assert (settings.question_limit, settings.session_hours, settings.sessions_per_ip_per_day) == (3, 12, 10)
    assert (settings.daily_total_limit, settings.attachment_limit) == (50, 0)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GUEST_MODE", "maybe"),
        ("GUEST_QUESTION_LIMIT", "0"),
        ("GUEST_QUESTION_LIMIT", "abc"),
        ("GUEST_SESSION_HOURS", "0"),
        ("GUEST_SESSIONS_PER_IP_PER_DAY", "-1"),
        ("GUEST_DAILY_TOTAL_LIMIT", "0"),
        ("GUEST_ATTACHMENT_LIMIT", "-2"),
    ],
)
def test_invalid_values_stop_the_start(name, value):
    with pytest.raises(GuestConfigError, match=name):
        load_guest_settings({name: value})
