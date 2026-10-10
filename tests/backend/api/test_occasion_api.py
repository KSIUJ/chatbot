"""Endpointy motywow okazjonalnych: GET /occasion i GET /occasion/facade/{wersja}.

Dane sa syntetyczne - repozytorium jest publiczne, a motywy ksi.sh i ich
terminy sa tajne (konkurs odznak).
"""

from __future__ import annotations

import pytest

from src.backend import main as main_module
from src.backend.occasion.router import get_occasion_store
from src.backend.occasion.state import Facade, OccasionSnapshot, OccasionStore

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    "<style>.f{fill:#111}@media (prefers-color-scheme:dark){.f{fill:#eee}}</style>"
    '<path class="f" d="M0 0h10v10H0z"/></svg>'
)
PL = Facade(version="0123456789abcdef", svg=SVG)
EN = Facade(version="fedcba9876543210", svg=SVG.replace("#111", "#222"))


@pytest.fixture
def store(client) -> OccasionStore:
    occasion_store = OccasionStore()
    main_module.app.dependency_overrides[get_occasion_store] = lambda: occasion_store
    return occasion_store


def active(**changes) -> OccasionSnapshot:
    values = {
        "dark": True,
        "theme_color": "#0b1a2a",
        "palette": {"night-950": "#0b1a2a", "accent": "#1d5c3a"},
        "facades": {"pl": PL, "en": EN},
    }
    values.update(changes)
    return OccasionSnapshot(**values)


def test_unknown_state_is_503_so_the_browser_keeps_its_cache(client, store):
    response = client.get("/occasion")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "occasion_unknown"
    assert response.headers["retry-after"]


def test_no_occasion(client, store):
    store.set(None)

    response = client.get("/occasion")

    assert response.status_code == 200
    assert response.json() == {"active": False, "dark": False, "theme_color": None, "palette": {}, "facade": None}
    assert response.headers["cache-control"] == "no-cache"


def test_active_occasion_without_login(client, store):
    store.set(active())

    response = client.get("/occasion")

    assert response.status_code == 200
    assert response.json() == {
        "active": True,
        "dark": True,
        "theme_color": "#0b1a2a",
        "palette": {"night-950": "#0b1a2a", "accent": "#1d5c3a"},
        "facade": {"pl": PL.version, "en": EN.version},
    }


def test_response_does_not_name_the_occasion(client, store):
    store.set(active())

    body = client.get("/occasion").json()

    assert set(body) == {"active", "dark", "theme_color", "palette", "facade"}


def test_active_occasion_without_facade(client, store):
    store.set(active(facades={}))

    assert client.get("/occasion").json()["facade"] is None


@pytest.mark.parametrize(("scheme", "fill"), [("light", "@media not all"), ("dark", "@media all")])
def test_facade_for_a_scheme(client, store, scheme, fill):
    store.set(active())

    response = client.get(f"/occasion/facade/{PL.version}", params={"scheme": scheme})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert fill in response.text
    assert "prefers-color-scheme" not in response.text
    assert response.headers["cache-control"] == "private, max-age=600"
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = response.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "script-src" not in csp


def test_second_language_facade(client, store):
    store.set(active())

    response = client.get(f"/occasion/facade/{EN.version}")

    assert response.status_code == 200
    assert "#222" in response.text


def test_facade_of_an_old_or_unknown_version_is_404(client, store):
    store.set(active())

    assert client.get("/occasion/facade/aaaaaaaaaaaaaaaa").status_code == 404

    store.set(None)
    assert client.get(f"/occasion/facade/{PL.version}").status_code == 404


@pytest.mark.parametrize("version", ["short", "0123456789ABCDEF", "0123456789abcdef0", "..%2F..%2Fetc"])
def test_malformed_version_is_rejected(client, store, version):
    store.set(active())

    assert client.get(f"/occasion/facade/{version}").status_code in (404, 422)


def test_unknown_scheme_is_rejected(client, store):
    store.set(active())

    assert client.get(f"/occasion/facade/{PL.version}", params={"scheme": "neon"}).status_code == 422


def test_post_is_not_allowed(client, store):
    assert client.post("/occasion").status_code == 405
