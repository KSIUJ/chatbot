"""Konfiguracja motywow okazjonalnych z env (src/backend/occasion/settings.py)."""

from __future__ import annotations

import pytest

from src.backend.occasion.settings import (
    DEFAULT_REFRESH_SECONDS,
    DEFAULT_SOURCE_URL,
    OccasionConfigError,
    load_occasion_settings,
)


def test_defaults():
    settings = load_occasion_settings({})

    assert settings.source_url == DEFAULT_SOURCE_URL
    assert settings.refresh_seconds == DEFAULT_REFRESH_SECONDS


@pytest.mark.parametrize("value", ["off", "OFF", " false ", "0", "no", "nie"])
def test_feature_can_be_switched_off(value):
    assert load_occasion_settings({"OCCASION_SOURCE_URL": value}).source_url is None


def test_custom_source_and_interval():
    settings = load_occasion_settings(
        {"OCCASION_SOURCE_URL": "http://127.0.0.1:9000/", "OCCASION_REFRESH_SECONDS": "30"}
    )

    assert settings.source_url == "http://127.0.0.1:9000/"
    assert settings.refresh_seconds == 30


@pytest.mark.parametrize(
    "url",
    [
        "ftp://ksi.sh/",
        "ksi.sh",
        "https://",
        "https://user:pass@ksi.sh/",
        "https://ksi.sh/?q=1",
        "https://ksi.sh/#x",
    ],
)
def test_bad_source_url_stops_the_start(url):
    with pytest.raises(OccasionConfigError):
        load_occasion_settings({"OCCASION_SOURCE_URL": url})


@pytest.mark.parametrize("value", ["abc", "0", "5", "3601", "-10"])
def test_bad_interval_stops_the_start(value):
    with pytest.raises(OccasionConfigError):
        load_occasion_settings({"OCCASION_REFRESH_SECONDS": value})
