"""Fasady SVG pobrane z ksi.sh: sprawdzenie przed podaniem z naszego originu
i wersje dla jasnego/ciemnego motywu czatu.

SVG z obcego zrodla podawany z chat.ksi.sh moglby wykonac skrypt w naszym
originie, gdyby ktos otworzyl go bezposrednio (nie jako <img>). Dlatego
przepuszczamy tylko elementy grafiki z listy, bez obslugi zdarzen, linkow,
zewnetrznych zasobow i DTD, a podajemy drzewo zapisane na nowo po
sprawdzeniu (bez komentarzy, instrukcji przetwarzania i deklaracji
kodowania) - przegladarka dostaje dokladnie to, co sprawdzilismy. Endpoint
dodaje do tego CSP bez skryptow.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Literal

MAX_SVG_BYTES = 1_000_000
MAX_ELEMENTS = 100_000

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# Elementy grafiki, gradientow, filtrow i animacji. Bez a, image, feImage,
# foreignObject, script, iframe, set (moze podmienic href na javascript:).
ALLOWED_TAGS = frozenset({
    "svg", "g", "defs", "symbol", "use", "title", "desc", "style",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "textPath",
    "linearGradient", "radialGradient", "stop", "pattern", "clipPath", "mask", "marker",
    "filter", "feGaussianBlur", "feDropShadow", "feOffset", "feBlend", "feFlood",
    "feComposite", "feMerge", "feMergeNode", "feColorMatrix", "feMorphology",
    "feTurbulence", "feDisplacementMap", "feComponentTransfer", "feFuncR", "feFuncG",
    "feFuncB", "feFuncA",
    "animate", "animateMotion", "animateTransform", "mpath",
})
# z przestrzeni xml: tylko te (xml:base zmienialby adres bazowy linkow)
ALLOWED_XML_ATTRS = frozenset({f"{{{XML_NS}}}space", f"{{{XML_NS}}}lang"})
# atrybuty, ktore wolno animowac (zadnych linkow)
ANIMATABLE = frozenset({
    "opacity", "fill-opacity", "stroke-opacity", "stop-opacity", "fill", "stroke", "stop-color",
    "stroke-width", "stroke-dashoffset", "stroke-dasharray", "transform", "d", "points",
    "x", "y", "cx", "cy", "r", "rx", "ry", "width", "height", "offset", "startOffset",
    "visibility", "display",
})
# funkcje CSS/SVG, ktore wolno uzyc (zadna nie laduje zasobu poza url(#id))
ALLOWED_FUNCTIONS = frozenset({
    "url", "rotate", "rotatex", "rotatey", "rotatez", "scale", "scalex", "scaley", "skew",
    "skewx", "skewy", "translate", "translatex", "translatey", "matrix", "steps",
    "cubic-bezier", "linear", "rgb", "rgba", "hsl", "hsla", "var", "calc", "min", "max",
    "clamp", "blur", "drop-shadow", "brightness", "opacity", "saturate", "hue-rotate",
    "contrast", "grayscale", "sepia", "invert",
})

_FORBIDDEN_TEXT = re.compile(r"javascript:|@import|expression\(|-moz-binding|behavior:", re.IGNORECASE)
# nazwa funkcji tuz przed "(" (bez "@media (" itp.)
_FUNCTION = re.compile(r"(?<![\w@-])([A-Za-z][\w-]*)\(")
# url(...) wolno tylko do elementow tego samego pliku: url(#id)
_EXTERNAL_URL = re.compile(r"""url\(\s*(?!['"]?#)""", re.IGNORECASE)
# ucieczki CSS (u\72l) pozwalaja ominac powyzsze wzorce
_CSS_ESCAPE = re.compile(r"\\")
# przegladarki pomijaja biale i sterujace znaki w "java\tscript:"
_IGNORED_CHARS = re.compile(r"[\x00-\x20]+")
_DTD = re.compile(r"<!DOCTYPE|<!ENTITY", re.IGNORECASE)
_COLOR_SCHEME_QUERY = re.compile(r"@media\s*\(\s*prefers-color-scheme\s*:\s*(dark|light)\s*\)", re.IGNORECASE)


class UnsafeSvg(ValueError):
    """Plik nie jest grafika SVG, ktora mozna bezpiecznie podac z naszego originu."""


def _split(name: str) -> tuple[str, str]:
    """'{ns}local' -> (ns, local)."""
    if name.startswith("{"):
        namespace, _, local = name[1:].partition("}")
        return namespace, local
    return "", name


def _check_css(text: str, where: str) -> None:
    compact = _IGNORED_CHARS.sub("", text)
    if _FORBIDDEN_TEXT.search(compact) or _EXTERNAL_URL.search(text) or _CSS_ESCAPE.search(text):
        raise UnsafeSvg(f"niedozwolona tresc w {where}")
    for name in _FUNCTION.findall(text):
        if name.lower() not in ALLOWED_FUNCTIONS:
            raise UnsafeSvg(f"niedozwolona funkcja {name}() w {where}")


def _check_attribute(tag: str, name: str, value: str) -> None:
    namespace, local = _split(name)
    if namespace == XML_NS and name not in ALLOWED_XML_ATTRS:
        raise UnsafeSvg(f"atrybut xml:{local} w <{tag}>")
    if namespace not in ("", XLINK_NS, XML_NS):
        raise UnsafeSvg(f"atrybut z obcej przestrzeni nazw w <{tag}>")
    if local.lower().startswith("on"):
        raise UnsafeSvg(f"obsluga zdarzenia {local} w <{tag}>")
    if local == "href" and not value.startswith("#"):
        raise UnsafeSvg(f"zewnetrzny link w <{tag}>")
    if local == "attributeName" and value.strip() not in ANIMATABLE:
        raise UnsafeSvg(f"animacja atrybutu {value.strip()!r} w <{tag}>")
    _check_css(value, f"atrybucie {local} <{tag}>")


def _href(element: ET.Element) -> str | None:
    return element.get("href") or element.get(f"{{{XLINK_NS}}}href")


def _check_use_fan_out(root: ET.Element) -> None:
    """<use> nie moze wskazywac na cos, co samo zawiera <use> - zagniezdzone
    powielanie (jak billion laughs) zawiesiloby przegladarke kazdego widza."""
    by_id = {element.get("id"): element for element in root.iter() if element.get("id")}
    use_tag = f"{{{SVG_NS}}}use"
    for use in root.iter(use_tag):
        target = by_id.get((_href(use) or "").removeprefix("#"))
        if target is not None and any(node.tag == use_tag for node in target.iter()):
            raise UnsafeSvg("zagniezdzone <use>")


def _check_tree(root: ET.Element) -> None:
    if root.tag != f"{{{SVG_NS}}}svg":
        raise UnsafeSvg("to nie jest SVG")
    for count, element in enumerate(root.iter(), start=1):
        if count > MAX_ELEMENTS:
            raise UnsafeSvg("za duzo elementow")
        namespace, tag = _split(element.tag)
        if namespace != SVG_NS or tag not in ALLOWED_TAGS:
            raise UnsafeSvg(f"niedozwolony element <{tag}>")
        for name, value in element.attrib.items():
            _check_attribute(tag, name, value)
        if tag == "style" and element.text:
            _check_css(element.text, "<style>")
    _check_use_fan_out(root)


def validate_svg(text: str) -> str:
    """Sprawdza fasade i zwraca ja zapisana na nowo z drzewa XML.

    Raises:
        UnsafeSvg: za duzy plik, DTD, nie-SVG, element spoza listy, obsluga
            zdarzen, zewnetrzny link/zasob, niedozwolona funkcja CSS,
            animacja spoza listy atrybutow albo zagniezdzone <use>.
    """
    if len(text.encode("utf-8")) > MAX_SVG_BYTES:
        raise UnsafeSvg("plik za duzy")
    if _DTD.search(text):
        raise UnsafeSvg("DTD/encje sa niedozwolone")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise UnsafeSvg("to nie jest poprawny XML") from error
    _check_tree(root)
    return _serialize(root)


def _serialize(root: ET.Element) -> str:
    """Zapis sprawdzonego drzewa: elementy bez prefiksow w przestrzeni SVG,
    linki jako xlink:href (zwykly zapis SVG, ktory przegladarki rozumieja)."""
    uses_xlink = False
    for element in root.iter():
        element.tag = _split(element.tag)[1]
        for name in [name for name in element.attrib if name.startswith(f"{{{XLINK_NS}}}")]:
            element.set(f"xlink:{_split(name)[1]}", element.attrib.pop(name))
            uses_xlink = True
    root.set("xmlns", SVG_NS)
    if uses_xlink:
        root.set("xmlns:xlink", XLINK_NS)
    return ET.tostring(root, encoding="unicode")


def for_scheme(text: str, scheme: Literal["light", "dark"]) -> str:
    """Wersja grafiki dla motywu czatu, a nie systemu.

    Fasady przelaczaja kolory przez @media (prefers-color-scheme), co w <img>
    zalezy od ustawien systemu - uzytkownik czatu moze miec inny motyw.
    Zapytanie pasujace do `scheme` zamienia sie w `@media all`, drugie
    w `@media not all`.
    """
    return _COLOR_SCHEME_QUERY.sub(
        lambda match: "@media all" if match.group(1).lower() == scheme else "@media not all",
        text,
    )
