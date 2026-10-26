"""Odczyt aktywnej okazji ze strony glownej KSI (src/backend/occasion/landing.py)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from src.backend.occasion.landing import (
    ApiResponseError,
    FacadePaths,
    parse_api_occasion,
    parse_facade_paths,
    parse_landing_page,
)

from occasion_samples import (
    COLOR,
    ENTRY_SCRIPT,
    FACADE_EN_PATH,
    FACADE_PATH,
    FACADE_PL_PATH,
    MODULE_PATH,
    OCCASION,
    entry_module,
    landing_html,
)


def test_reads_occasion_color_palette_and_entry_module():
    page = parse_landing_page(landing_html())

    assert page.occasion == OCCASION
    assert page.color == COLOR
    assert page.entry_module == MODULE_PATH
    assert page.palette["night-950"] == "#0b1a2a"
    assert page.palette["accent"] == "#1d5c3a"
    assert len(page.palette) == 12


def test_page_without_occasion_is_inactive_and_ignores_the_rest():
    page = parse_landing_page(landing_html(occasion=None))

    assert page.occasion is None
    assert page.color is None
    assert page.palette == {}
    assert page.entry_module is None


def test_critical_css_root_is_not_taken_for_an_occasion_palette():
    page = parse_landing_page(landing_html(palette=None))

    assert page.occasion == OCCASION
    assert page.palette == {}


def test_occasion_without_color_does_not_force_dark():
    page = parse_landing_page(landing_html(color=None))

    assert page.occasion == OCCASION
    assert page.color is None


@pytest.mark.parametrize(
    "occasion",
    ["", "UPPER", "with space", "x" * 41, "a/b", "<script>", 'q"x'],
)
def test_malformed_occasion_id_counts_as_no_occasion(occasion):
    html = landing_html().replace(f'data-occasion="{OCCASION}"', f"data-occasion='{occasion}'")

    assert parse_landing_page(html).occasion is None


@pytest.mark.parametrize("color", ["red", "#fff", "#12345g", "#1234567", "url(x)", "#0b1a2a;x"])
def test_malformed_color_is_dropped(color):
    assert parse_landing_page(landing_html(color=color)).color is None


def test_palette_keeps_only_known_variables_and_hex_values():
    palette = ":root { --color-night-950: #000000; --color-unknown: #111111; --color-accent: #222222; }"

    page = parse_landing_page(landing_html(palette=palette))

    assert page.palette == {"night-950": "#000000", "accent": "#222222"}


@pytest.mark.parametrize(
    "palette",
    [
        ":root { --color-night-950: red; }",
        ":root { --color-night-950: #000000; } body { background: url(https://evil.test/x) }",
        "html { --color-night-950: #000000; }",
        ":root { --color-night-950: #000000; --font: x; }",
    ],
)
def test_style_blocks_that_are_not_a_pure_color_root_are_ignored(palette):
    assert parse_landing_page(landing_html(palette=palette)).palette == {}


def test_hostile_palette_block_is_parsed_in_linear_time():
    # whitespace-separated declarations ending in garbage made the old regex backtrack exponentially
    hostile = ":root{" + "--color-a:#000000   " * 40 + "x}"
    started = time.perf_counter()

    page = parse_landing_page(landing_html(palette=hostile))

    assert page.palette == {}
    assert time.perf_counter() - started < 1


def test_huge_style_block_is_not_a_palette():
    palette = ":root { " + "--color-accent: #000000; " * 400 + "}"

    assert parse_landing_page(landing_html(palette=palette)).palette == {}


def test_facade_object_with_many_pairs_is_parsed_quickly():
    pairs = ",".join(f"k{i}:a" for i in range(5000))
    module = "x" * 200_000 + entry_module(facade="{" + pairs + ",pl:p}")
    started = time.perf_counter()

    paths = parse_facade_paths(module, OCCASION)

    assert paths == FacadePaths(pl=FACADE_PL_PATH, en=FACADE_PL_PATH)
    assert time.perf_counter() - started < 1


def test_entry_module_must_be_a_single_local_asset_path():
    scripts = (
        '<script>import("/assets/One1.js")</script><script>import("/assets/Two2.js")</script>',
        '<script>import("https://evil.test/assets/x.js")</script>',
        '<script>import("/assets/../secret.js")</script>',
        '<script>import("/other/x.js")</script>',
    )
    for script in scripts:
        assert parse_landing_page(landing_html(entry_script=script)).entry_module is None


def test_entry_import_inside_a_data_attribute_or_text_is_not_a_script():
    html = landing_html(entry_script=None).replace(
        "<h1>Strona</h1>", f'<h1 title=\'import("{MODULE_PATH}")\'>import("{MODULE_PATH}")</h1>'
    )

    assert parse_landing_page(html).entry_module is None


def test_only_the_first_html_tag_counts():
    html = landing_html(occasion=None).replace(
        "<div id=root>", '<div id=root><html data-occasion="injected" data-color="#000000">'
    )

    page = parse_landing_page(html)

    assert page.occasion is None
    assert page.color is None


def test_broken_markup_does_not_raise():
    page = parse_landing_page("<html data-occasion=" + "<" * 1000 + ENTRY_SCRIPT[:20])

    assert page.entry_module is None


def test_facade_from_a_constant_is_used_for_both_languages():
    assert parse_facade_paths(entry_module(), OCCASION) == FacadePaths(pl=FACADE_PATH, en=FACADE_PATH)


def test_facade_from_a_string_literal():
    module = entry_module(facade=f'"{FACADE_PATH}"')

    assert parse_facade_paths(module, OCCASION) == FacadePaths(pl=FACADE_PATH, en=FACADE_PATH)


def test_facade_per_language():
    module = entry_module(facade="{pl:p,en:q}")

    assert parse_facade_paths(module, OCCASION) == FacadePaths(pl=FACADE_PL_PATH, en=FACADE_EN_PATH)


def test_facade_with_one_language_is_used_for_both():
    module = entry_module(facade="{pl:p}")

    assert parse_facade_paths(module, OCCASION) == FacadePaths(pl=FACADE_PL_PATH, en=FACADE_PL_PATH)


def test_module_of_another_occasion_is_rejected():
    assert parse_facade_paths(entry_module(occasion="other-one"), OCCASION) is None


@pytest.mark.parametrize(
    "facade",
    [
        "zz",  # niezdefiniowana stala
        '"https://evil.test/x.svg"',
        '"/assets/../x.svg"',
        '"/assets/x.png"',
        '"data:image/svg+xml,<svg/>"',
        "{de:p}",
    ],
)
def test_unusable_facade_gives_none(facade):
    assert parse_facade_paths(entry_module(facade=facade), OCCASION) is None


def test_module_without_facade_gives_none():
    module = entry_module().replace("facade:a", "notFound:a")

    assert parse_facade_paths(module, OCCASION) is None


# --- API ksi.sh (/api/occasion) ------------------------------------------------

NOW = datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc)


def _api_body(occasion: object = OCCASION, start: object = "2030-01-10T10:00:00.000Z",
              end: object = "2030-01-15T13:00:00.000Z") -> str:
    return json.dumps({"occasion": occasion, "start": start, "end": end})


def test_api_running_occasion_with_seconds_to_its_end():
    api = parse_api_occasion(_api_body(), NOW)

    assert api is not None and api.occasion == OCCASION
    assert api.ends_in == timedelta(hours=1).total_seconds()
    # termin konca nie trafia do logu przy wypisaniu obiektu
    assert "3600" not in repr(api)


@pytest.mark.parametrize("body", ['{"occasion": null}', '{"occasion": ""}', "{}"])
def test_api_without_occasion_gives_none(body):
    assert parse_api_occasion(body, NOW) is None


def test_api_occasion_outside_its_dates_gives_none():
    assert parse_api_occasion(_api_body(start="2030-01-16T00:00:00Z"), NOW) is None
    assert parse_api_occasion(_api_body(end="2030-01-15T12:00:00Z"), NOW) is None


def test_api_occasion_without_dates_has_no_known_end():
    api = parse_api_occasion(json.dumps({"occasion": OCCASION}), NOW)

    assert api is not None and api.ends_in is None


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        _api_body(occasion="Bad Id!"),
        _api_body(occasion=7),
        _api_body(end="tomorrow"),
        _api_body(end="2030-01-15T13:00:00"),  # bez strefy
        _api_body(start=12345),
    ],
)
def test_api_in_unknown_shape_raises(body):
    with pytest.raises(ApiResponseError):
        parse_api_occasion(body, NOW)


def test_template_literal_build_of_the_landing_page():
    # nowszy build ksi.sh: import(`...`) i facade:`...` w backtickach (2026-10)
    script = f"<script type=module>for(let e of[`a`])addEventListener(e,t);import(`{MODULE_PATH}`)</script>"
    page = parse_landing_page(landing_html(entry_script=script))
    module = (
        'import{n as e,t}from"./DP0jm0rX.js";'
        f"t({{occasion:`{OCCASION}`,name:{{pl:`X`,en:`X`}},decorations:()=>e(()=>import(`./a.js`)),facade:`{FACADE_PATH}`}});"
    )

    assert page.occasion == OCCASION and page.entry_module == MODULE_PATH
    assert parse_facade_paths(module, OCCASION) == FacadePaths(pl=FACADE_PATH, en=FACADE_PATH)


def test_template_literal_with_interpolation_is_not_a_path():
    module = f"t({{occasion:`{OCCASION}`,facade:`/assets/${{x}}.svg`}});"

    assert parse_facade_paths(module, OCCASION) is None
