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


# Zmyslony token (prawdziwy jest tylko w .env na serwerze).
TOKEN = "test-token-0123456789abcdef"


def test_api_token_is_optional_and_kept_out_of_repr():
    assert load_occasion_settings({}).api_token is None

    settings = load_occasion_settings({"OCCASION_API_TOKEN": f"  {TOKEN} "})

    assert settings.api_token == TOKEN
    assert TOKEN not in repr(settings)


def test_api_token_is_ignored_when_the_feature_is_off():
    assert load_occasion_settings({"OCCASION_SOURCE_URL": "off", "OCCASION_API_TOKEN": TOKEN}).api_token is None


@pytest.mark.parametrize("token", ["short", "has space inside 0123456789", "line\nbreak0123456789abc"])
def test_malformed_api_token_stops_the_start(token):
    with pytest.raises(OccasionConfigError):
        load_occasion_settings({"OCCASION_API_TOKEN": token})


def test_api_token_is_never_sent_over_plain_http():
    with pytest.raises(OccasionConfigError):
        load_occasion_settings({"OCCASION_SOURCE_URL": "http://127.0.0.1:9000/", "OCCASION_API_TOKEN": TOKEN})
