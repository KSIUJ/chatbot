"""Odswiezanie stanu okazji z ksi.sh: pobieranie, pamiec podreczna zasobow,
stary stan przy awarii (src/backend/occasion/state.py)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from datetime import datetime, timezone

import httpx
import pytest

from src.backend.occasion import state as state_module
from src.backend.occasion.svg import validate_svg
from src.backend.occasion.state import (
    STALE_AFTER_SECONDS,
    LandingClient,
    LandingError,
    OccasionSnapshot,
    OccasionStore,
    refresh_loop,
    refresh_once,
)

from occasion_samples import (
    COLOR,
    FACADE_EN_PATH,
    FACADE_PATH,
    FACADE_PL_PATH,
    FACADE_SVG,
    MODULE_PATH,
    OCCASION,
    entry_module,
    landing_html,
)

SOURCE = "https://landing.test/"


class FakeLanding:
    """Atrapa strony glownej: sciezka -> (status, tresc); liczy zapytania."""

    def __init__(self, pages: dict[str, tuple[int, str]]):
        self.pages = pages
        self.requests: Counter[str] = Counter()
        self.user_agents: set[str] = set()
        # sciezki, pod ktore poszedl naglowek Authorization
        self.authorized: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests[request.url.path] += 1
        self.user_agents.add(request.headers.get("user-agent", ""))
        if "authorization" in request.headers:
            self.authorized.add(request.url.path)
        if request.url.host != "landing.test":
            return httpx.Response(599)
        status, body = self.pages.get(request.url.path, (404, "Not found"))
        return httpx.Response(status, text=body)


def default_pages(**overrides: tuple[int, str]) -> dict[str, tuple[int, str]]:
    pages = {
        "/": (200, landing_html()),
        MODULE_PATH: (200, entry_module()),
        FACADE_PATH: (200, FACADE_SVG),
    }
    pages.update(overrides)
    return pages


def fetch(landing: FakeLanding, client: LandingClient | None = None) -> OccasionSnapshot | None:
    """Jedno pobranie przez atrape; `client` pozwala sprawdzic pamiec miedzy pobraniami."""

    async def run() -> OccasionSnapshot | None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(landing.handler)) as http:
            used = client or LandingClient(http, SOURCE)
            used.http = http
            return await used.fetch()

    return asyncio.run(run())


def test_active_occasion_with_palette_and_facade():
    landing = FakeLanding(default_pages())

    snapshot = fetch(landing)

    assert snapshot is not None
    assert snapshot.dark is True
    assert snapshot.theme_color == COLOR
    assert snapshot.palette["night-950"] == "#0b1a2a"
    # served text is the re-serialized, checked tree
    assert snapshot.facades["pl"].svg == validate_svg(FACADE_SVG)
    assert "@media all" in snapshot.facades["pl"].dark
    assert "@media not all" in snapshot.facades["pl"].light
    assert snapshot.facades["pl"] is snapshot.facades["en"]
    assert len(snapshot.facades["pl"].version) == 16
    assert all("KSI-Chatbot" in agent for agent in landing.user_agents)


def test_no_occasion_gives_none_without_fetching_assets():
    landing = FakeLanding(default_pages(**{"/": (200, landing_html(occasion=None))}))

    assert fetch(landing) is None
    assert landing.requests[MODULE_PATH] == 0


def test_occasion_without_color_follows_the_user_theme():
    landing = FakeLanding(default_pages(**{"/": (200, landing_html(color=None))}))

    snapshot = fetch(landing)

    assert snapshot is not None
    assert snapshot.dark is False
    assert snapshot.theme_color is None


def test_per_language_facades_are_fetched_separately():
    landing = FakeLanding(
        default_pages(
            **{
                MODULE_PATH: (200, entry_module(facade="{pl:p,en:q}")),
                FACADE_PL_PATH: (200, FACADE_SVG),
                FACADE_EN_PATH: (200, FACADE_SVG.replace("KSI", "EN")),
            }
        )
    )

    snapshot = fetch(landing)

    assert snapshot is not None
    assert snapshot.facades["pl"].version != snapshot.facades["en"].version
    assert "EN" in snapshot.facades["en"].svg


@pytest.mark.parametrize(
    "overrides",
    [
        {MODULE_PATH: (404, "Not found")},
        {MODULE_PATH: (200, "garbage")},
        {FACADE_PATH: (500, "boom")},
        {FACADE_PATH: (200, "<svg xmlns='http://www.w3.org/2000/svg'><script>x</script></svg>")},
    ],
)
def test_broken_facade_keeps_the_colors(overrides):
    landing = FakeLanding(default_pages(**overrides))

    snapshot = fetch(landing)

    assert snapshot is not None
    assert snapshot.dark is True
    assert snapshot.facades == {}


@pytest.mark.parametrize("status", [301, 403, 500, 503])
def test_landing_error_status_raises(status):
    landing = FakeLanding(default_pages(**{"/": (status, "nope")}))

    with pytest.raises(LandingError):
        fetch(landing)


def test_too_large_page_raises():
    landing = FakeLanding(default_pages(**{"/": (200, landing_html() + "x" * 2_100_000)}))

    with pytest.raises(LandingError):
        fetch(landing)


def test_assets_are_cached_between_refreshes():
    landing = FakeLanding(default_pages())
    client = LandingClient(None, SOURCE)  # type: ignore[arg-type]

    first = fetch(landing, client)
    second = fetch(landing, client)

    assert first == second
    assert landing.requests["/"] == 2
    assert landing.requests[MODULE_PATH] == 1
    assert landing.requests[FACADE_PATH] == 1


def test_failed_asset_is_retried_on_the_next_refresh():
    landing = FakeLanding(default_pages(**{FACADE_PATH: (503, "busy")}))
    client = LandingClient(None, SOURCE)  # type: ignore[arg-type]

    assert fetch(landing, client).facades == {}
    landing.pages[FACADE_PATH] = (200, FACADE_SVG)
    assert fetch(landing, client).facades["pl"].svg == validate_svg(FACADE_SVG)


def test_asset_urls_stay_on_the_source_origin():
    landing = FakeLanding(default_pages())

    fetch(landing)

    assert set(landing.requests) == {"/", MODULE_PATH, FACADE_PATH}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def snapshot_sample() -> OccasionSnapshot:
    return OccasionSnapshot(dark=True, theme_color=COLOR, palette={}, facades={})


def test_store_is_unknown_until_the_first_refresh():
    store = OccasionStore(clock=Clock())

    assert store.known is False


def test_store_keeps_the_last_snapshot_for_a_while_after_failures():
    clock = Clock()
    store = OccasionStore(clock=clock)
    store.set(snapshot_sample())

    clock.now += STALE_AFTER_SECONDS - 1
    store.failed()
    assert store.known is True
    assert store.current() == snapshot_sample()

    clock.now += 2
    assert store.current() is None


def test_store_stays_unknown_after_early_failures_then_gives_up():
    clock = Clock()
    store = OccasionStore(clock=clock)

    store.failed()
    clock.now += STALE_AFTER_SECONDS - 1
    store.failed()
    # browsers keep their last state while ksi.sh is down right after a restart
    assert store.known is False

    clock.now += 2
    assert store.known is True
    assert store.current() is None


def test_store_finds_facades_only_of_the_current_snapshot():
    landing = FakeLanding(default_pages())
    snapshot = fetch(landing)
    assert snapshot is not None
    store = OccasionStore(clock=Clock())
    store.set(snapshot)
    version = snapshot.facades["pl"].version

    assert store.facade(version) == snapshot.facades["pl"]
    assert store.facade("0" * 16) is None

    store.set(None)
    assert store.facade(version) is None


def test_refresh_once_records_failures_instead_of_raising():
    landing = FakeLanding(default_pages(**{"/": (500, "down")}))
    store = OccasionStore(clock=Clock())

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(landing.handler)) as http:
            await refresh_once(store, LandingClient(http, SOURCE))

    asyncio.run(run())

    assert store.known is False
    assert store.current() is None


def test_remote_charset_is_ignored_and_utf8_is_used():
    body = landing_html().encode("utf-8")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("accept-encoding", ""))
        return httpx.Response(200, content=body, headers={"content-type": "text/html; charset=no-such-codec"})

    async def run() -> OccasionSnapshot | None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await LandingClient(http, SOURCE).fetch()

    assert asyncio.run(run()) is not None
    # no compression: the size cap counts real bytes, a gzip bomb cannot inflate past it
    assert seen and all(value == "identity" for value in seen)


def test_slow_landing_hits_the_refresh_deadline(monkeypatch: pytest.MonkeyPatch):
    async def hanging(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, text=landing_html())

    monkeypatch.setattr(state_module, "REFRESH_DEADLINE_SECONDS", 0.05)
    store = OccasionStore(clock=Clock())

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(hanging)) as http:
            await refresh_once(store, LandingClient(http, SOURCE))

    asyncio.run(run())

    assert store.current() is None
    assert store._first_failure_at is not None


def test_refresh_loop_survives_unexpected_errors_and_stops_on_cancel(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def broken_fetch(_self: LandingClient) -> OccasionSnapshot | None:
        calls.append("fetch")
        raise RuntimeError("parser bug")

    monkeypatch.setattr(LandingClient, "fetch", broken_fetch)
    store = OccasionStore(clock=Clock())

    async def run() -> None:
        task = asyncio.create_task(refresh_loop(store, SOURCE, 0))
        while len(calls) < 3:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    assert len(calls) >= 3
    assert store._first_failure_at is not None


def test_refresh_once_survives_network_errors():
    def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    store = OccasionStore(clock=Clock())

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as http:
            await refresh_once(store, LandingClient(http, SOURCE))

    asyncio.run(run())

    assert store.current() is None


# --- API ksi.sh -------------------------------------------------------------------

TOKEN = "test-token-0123456789abcdef"
API_NOW = datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc)


def api_page(occasion: str | None = OCCASION, end: str = "2030-01-15T13:00:00Z") -> tuple[int, str]:
    return 200, json.dumps({"occasion": occasion, "start": "2030-01-10T10:00:00Z", "end": end})


def api_client() -> LandingClient:
    """Klient z tokenem i stala chwila (http podstawia fetch)."""
    return LandingClient(None, SOURCE, api_token=TOKEN, now=lambda: API_NOW)  # type: ignore[arg-type]


def test_api_decides_and_the_landing_page_gives_the_look():
    landing = FakeLanding(default_pages(**{"/api/occasion": api_page()}))

    snapshot = fetch(landing, api_client())

    assert snapshot is not None
    assert snapshot.palette["night-950"] == "#0b1a2a"
    assert snapshot.facades["pl"].svg == validate_svg(FACADE_SVG)
    assert snapshot.ends_in == 3600
    # token tylko do API, nigdy do strony ani plikow /assets/
    assert landing.authorized == {"/api/occasion"}


def test_api_without_occasion_skips_the_landing_page():
    landing = FakeLanding(default_pages(**{"/api/occasion": api_page(occasion=None)}))

    assert fetch(landing, api_client()) is None
    assert landing.requests["/"] == 0
    assert landing.requests[MODULE_PATH] == 0


def test_page_showing_another_occasion_than_the_api_gives_no_theme():
    landing = FakeLanding(default_pages(**{"/api/occasion": api_page(occasion="other-one")}))

    assert fetch(landing, api_client()) is None
    assert landing.requests[MODULE_PATH] == 0


@pytest.mark.parametrize("api", [(404, "Not found"), (500, "boom"), (200, "not json")])
def test_unusable_api_falls_back_to_the_landing_page_and_warns_once(api, caplog):
    landing = FakeLanding(default_pages(**{"/api/occasion": api}))
    client = api_client()

    with caplog.at_level(logging.WARNING, logger=state_module.__name__):
        first = fetch(landing, client)
        second = fetch(landing, client)

    assert first is not None and second is not None
    assert first.ends_in is None
    assert first.palette["night-950"] == "#0b1a2a"
    assert sum("API not used" in record.getMessage() for record in caplog.records) == 1
    assert TOKEN not in caplog.text


def test_without_a_token_the_api_is_not_asked():
    landing = FakeLanding(default_pages(**{"/api/occasion": api_page()}))

    assert fetch(landing) is not None
    assert landing.requests["/api/occasion"] == 0
    assert landing.authorized == set()


def test_store_drops_the_occasion_at_its_end_between_refreshes():
    clock = Clock()
    store = OccasionStore(clock=clock)
    store.set(OccasionSnapshot(dark=True, theme_color=COLOR, ends_in=120))

    clock.now += 119
    assert store.current() is not None

    clock.now += 1
    assert store.current() is None
    assert "120" not in repr(OccasionSnapshot(dark=True, theme_color=COLOR, ends_in=120))
