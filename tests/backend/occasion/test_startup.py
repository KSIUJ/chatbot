"""Start odswiezania motywu w lifespan (src/backend/main.py start_occasion_task)."""

from __future__ import annotations

import asyncio

import pytest

from src.backend import main as main_module
from src.backend.occasion.settings import get_occasion_settings
from src.backend.occasion.state import get_occasion_store


@pytest.fixture
def fresh_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OCCASION_REFRESH_SECONDS", raising=False)
    # src/backend/__init__.py wczytuje .env - prawdziwy token nie moze wplywac na test
    monkeypatch.delenv("OCCASION_API_TOKEN", raising=False)
    get_occasion_settings.cache_clear()
    get_occasion_store.cache_clear()
    yield
    get_occasion_settings.cache_clear()
    get_occasion_store.cache_clear()


def test_switched_off_feature_starts_no_task_and_shows_no_occasion(monkeypatch, fresh_state):
    monkeypatch.setenv("OCCASION_SOURCE_URL", "off")

    task = main_module.start_occasion_task()

    store = get_occasion_store()
    assert task is None
    assert store.known is True
    assert store.current() is None


def test_enabled_feature_starts_the_refresh_loop(monkeypatch, fresh_state):
    monkeypatch.setenv("OCCASION_SOURCE_URL", "https://landing.test/")
    started: list[tuple[str, int]] = []

    async def fake_loop(_store, source_url: str, interval: int, api_token: str | None = None) -> None:
        started.append((source_url, interval, api_token))

    monkeypatch.setattr(main_module, "refresh_loop", fake_loop)

    async def run() -> None:
        task = main_module.start_occasion_task()
        assert task is not None
        await task

    asyncio.run(run())

    assert started == [("https://landing.test/", 60, None)]
