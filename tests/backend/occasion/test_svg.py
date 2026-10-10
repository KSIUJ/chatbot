"""Sprawdzanie fasad SVG z ksi.sh przed podaniem ich z naszego originu
(src/backend/occasion/svg.py)."""

from __future__ import annotations

import pytest

from src.backend.occasion.svg import MAX_SVG_BYTES, UnsafeSvg, for_scheme, validate_svg

from occasion_samples import FACADE_SVG, SVG_NS


def svg(body: str, *, root_attrs: str = "") -> str:
    return f'<svg {SVG_NS} {root_attrs} viewBox="0 0 10 10">{body}</svg>'


def test_facade_like_svg_passes():
    validate_svg(FACADE_SVG)


@pytest.mark.parametrize(
    "body",
    [
        "<script>alert(1)</script>",
        '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject>',
        '<a href="#x"><rect width="1" height="1"/></a>',
        '<image href="https://evil.test/x.png"/>',
        '<iframe src="https://evil.test"/>',
        '<rect onload="alert(1)" width="1" height="1"/>',
        '<rect ONCLICK="alert(1)" width="1" height="1"/>',
        '<use href="https://evil.test/x.svg#a"/>',
        '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="data:image/svg+xml,x"/>',
        '<rect style="fill:url(https://evil.test/a)" width="1" height="1"/>',
        '<rect fill="url( \'//evil.test/a\' )" width="1" height="1"/>',
        "<style>@import url(https://evil.test/x.css);</style>",
        "<style>.a{background:url(https://evil.test/beacon)}</style>",
        "<style>.a{background:u\\72l(https://evil.test/beacon)}</style>",
        "<style>.a{background:image-set(\"https://evil.test/a.png\" 1x)}</style>",
        "<style>@font-face{font-family:x;src(\"https://evil.test/f.woff\")}</style>",
        '<rect style="fill:image(\'https://evil.test/a\')" width="1" height="1"/>',
        '<set attributeName="href" to="javascript:alert(1)"/>',
        '<animate attributeName="xlink:href" values="javascript:alert(1)"/>',
        '<rect fill="javascript:alert(1)" width="1" height="1"/>',
        '<h:div xmlns:h="http://www.w3.org/1999/xhtml">x</h:div>',
        '<rect xmlns:ev="http://www.w3.org/2001/xml-events" ev:event="click" width="1" height="1"/>',
    ],
)
def test_dangerous_content_is_rejected(body):
    with pytest.raises(UnsafeSvg):
        validate_svg(svg(body))


@pytest.mark.parametrize(
    "body",
    [
        '<use xml:base="https://evil.test/" href="#a"/>',
        '<animate attributeName=" href" to="https://evil.test/x.svg#a"/>',
        '<animate attributeName="href&#10;" to="https://evil.test/x.svg#a"/>',
        '<animate attributeName="opacity" to="java&#9;script:alert(1)"/>',
        "<style>.a{background:attr(data-x)}</style>",
        "<style>.a{width:env(safe-area-inset-top)}</style>",
        '<rect transform="paint(x)" width="1" height="1"/>',
    ],
)
def test_allowlist_bypasses_are_rejected(body):
    with pytest.raises(UnsafeSvg):
        validate_svg(svg(body))


def test_nested_use_fan_out_is_rejected():
    body = (
        '<defs><g id="a"><rect width="1" height="1"/></g>'
        '<g id="b"><use href="#a"/><use href="#a"/></g></defs>'
        '<use href="#b"/>'
    )
    with pytest.raises(UnsafeSvg):
        validate_svg(svg(body))


def test_served_text_is_the_checked_tree_without_comments_or_instructions():
    text = (
        '<?xml version="1.0" encoding="UTF-7"?><?xml-stylesheet href="https://evil.test/x.css"?>'
        f'<svg {SVG_NS} xml:space="preserve"><!-- note --><style>.a{{fill:#fff}}</style>'
        '<rect class="a" transform="rotate(8 1 1)" width="1" height="1"/></svg>'
    )

    out = validate_svg(text)

    assert "<?" not in out and "<!--" not in out and "evil" not in out
    assert out.startswith("<svg ") and 'xmlns="http://www.w3.org/2000/svg"' in out
    assert "<style>.a{fill:#fff}</style>" in out
    assert 'xml:space="preserve"' in out
    # the result is itself a valid facade
    assert validate_svg(out) == out


def test_doctype_and_entities_are_rejected_before_parsing():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        f"<svg {SVG_NS}><text>&b;</text></svg>"
    )
    with pytest.raises(UnsafeSvg):
        validate_svg(bomb)


@pytest.mark.parametrize(
    "text",
    ["", "not xml", "<svg", "<html><body/></html>", '<svg xmlns="http://example.test/other"/>'],
)
def test_non_svg_is_rejected(text):
    with pytest.raises(UnsafeSvg):
        validate_svg(text)


def test_too_large_svg_is_rejected():
    big = svg("<!--" + "x" * MAX_SVG_BYTES + "-->")
    with pytest.raises(UnsafeSvg):
        validate_svg(big)


def test_local_references_are_allowed():
    validate_svg(
        svg(
            '<defs><clipPath id="c"><rect width="1" height="1"/></clipPath></defs>'
            '<rect clip-path="url(#c)" style="mask:url(#c)" width="1" height="1"/>'
            "<style>.x{filter:url(#c)}</style>"
        )
    )


def test_dark_scheme_turns_the_dark_media_query_on():
    out = for_scheme(FACADE_SVG, "dark")

    assert "prefers-color-scheme" not in out
    assert "@media all{.facade{fill:#2f3143}}" in out
    # inne zapytania (ograniczenie ruchu) zostaja bez zmian
    assert "@media (prefers-reduced-motion:reduce)" in out


def test_light_scheme_turns_the_dark_media_query_off():
    out = for_scheme(FACADE_SVG, "light")

    assert "@media not all{.facade{fill:#2f3143}}" in out


def test_scheme_rewrite_handles_spacing_and_light_queries():
    text = "<style>@media ( prefers-color-scheme : dark ){a{}}@media (prefers-color-scheme: light){b{}}</style>"

    assert for_scheme(text, "dark") == "<style>@media all{a{}}@media not all{b{}}</style>"
    assert for_scheme(text, "light") == "<style>@media not all{a{}}@media all{b{}}</style>"
