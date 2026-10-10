"""Odczyt aktywnej okazji ze strony glownej KSI (ksi.sh).

Strona sama decyduje, jaki motyw trwa, i wysyla tylko jego (harmonogram jest
tajny - konkurs odznak). Czytamy z niej:

- `<html data-occasion="..." data-color="#rrggbb">`: identyfikator okazji
  (traktowany jako nieprzezroczysty klucz) i kolor, ktory oznacza, ze strona
  wymusza ciemny motyw;
- blok `<style>:root { --color-night-950: #...; ... }</style>`: paleta okazji
  (krytyczny CSS strony tez ma :root, ale z innymi deklaracjami);
- modul wejsciowy okazji (`import("/assets/....js")` w skrypcie strony),
  w ktorym jest adres fasady: `facade:a` (stala) albo `facade:{pl:a,en:b}`.

To odczyt cudzej, zminifikowanej strony, wiec wszystko jest sprawdzane
wzorcami, a cos nieoczekiwanego daje "brak" zamiast bledu. Gdy landing dostanie
/api/occasion, wystarczy podmienic ten modul.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

OCCASION_ID = re.compile(r"[a-z0-9-]{1,40}")
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
# Jedyne zmienne palety, ktore bierzemy (te, ktore landing nadpisuje dla okazji).
PALETTE_VARS = frozenset({
    "night-950", "night-900", "night-800", "night-700", "night-600",
    "night-400", "night-300", "night-200", "night-100",
    "accent", "accent-hover", "accent-light",
})
# Blok palety jest maly; dluzszy <style> to inny CSS (np. krytyczny strony).
MAX_PALETTE_BLOCK = 4_000
# Bez zagniezdzonych kwantyfikatorow: cialo :root dzielimy na ";" i kazda
# deklaracje sprawdzamy osobno - czas liniowy niezaleznie od tresci strony.
_ROOT_RULE = re.compile(r":root\s*\{([^{}]*)\}")
_PALETTE_DECL = re.compile(r"\s*--color-([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*")
# Sciezki bez kropek poza rozszerzeniem: zadnego "..", zadnego innego hosta.
_ENTRY_IMPORT = re.compile(r"""\bimport\(\s*(["'])(/assets/[A-Za-z0-9_-]+\.js)\1\s*\)""")
SVG_PATH = re.compile(r"/assets/[A-Za-z0-9_-]+\.svg")
_IDENT = r"[A-Za-z_$][\w$]*"
_FACADE_KEY = re.compile(r"\bfacade\s*:\s*")
_STRING_VALUE = re.compile(r"""(["'])([^"'\\]*)\1""")
_IDENT_VALUE = re.compile(_IDENT)
_OBJECT_VALUE = re.compile(r"\{([^{}]*)\}")
_OBJECT_PAIR = re.compile(rf"""({_IDENT})\s*:\s*(?:(["'])([^"'\\]*)\2|({_IDENT}))""")
LANGUAGES = ("pl", "en")


@dataclass(frozen=True)
class LandingPage:
    # None = brak okazji (zwykly wyglad); reszta ma sens tylko przy okazji
    occasion: str | None
    color: str | None = None
    palette: dict[str, str] = field(default_factory=dict)
    entry_module: str | None = None


@dataclass(frozen=True)
class FacadePaths:
    pl: str
    en: str


class _PageParser(HTMLParser):
    """Zbiera atrybuty pierwszego <html>, tresc <style> i skryptow."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_attrs: dict[str, str] | None = None
        self.styles: list[str] = []
        self.scripts: list[str] = []
        self._open: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "html" and self.html_attrs is None:
            self.html_attrs = {name: value or "" for name, value in attrs}
        elif tag in ("style", "script"):
            self._open = tag
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self._open:
            return
        target = self.styles if tag == "style" else self.scripts
        target.append("".join(self._buffer))
        self._open = None


def _palette_block(style: str) -> dict[str, str] | None:
    """{zmienna: kolor} z bloku `:root { --color-x: #rrggbb; ... }`; None, gdy
    <style> zawiera cokolwiek innego."""
    text = style.strip()
    if len(text) > MAX_PALETTE_BLOCK or (rule := _ROOT_RULE.fullmatch(text)) is None:
        return None
    declarations = [part for part in rule.group(1).split(";") if part.strip()]
    matches = [_PALETTE_DECL.fullmatch(part) for part in declarations]
    if not matches or any(match is None for match in matches):
        return None
    return {match.group(1): match.group(2).lower() for match in matches if match is not None}


def _palette(styles: list[str]) -> dict[str, str]:
    """Ostatni blok skladajacy sie wylacznie z :root z kolorami (jak w kaskadzie)."""
    palette: dict[str, str] = {}
    for style in styles:
        block = _palette_block(style)
        if block is not None:
            palette = {name: value for name, value in block.items() if name in PALETTE_VARS}
    return palette


def _entry_module(scripts: list[str]) -> str | None:
    """Jedyny modul ladowany dynamicznie ze skryptu strony; kilka albo zero = brak."""
    paths = {match.group(2) for script in scripts for match in _ENTRY_IMPORT.finditer(script)}
    return paths.pop() if len(paths) == 1 else None


def parse_landing_page(html: str) -> LandingPage:
    """Okazja, kolor, paleta i modul wejsciowy z HTML strony glownej."""
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    attrs = parser.html_attrs or {}
    occasion = attrs.get("data-occasion", "")
    if OCCASION_ID.fullmatch(occasion) is None:
        return LandingPage(occasion=None)
    color = attrs.get("data-color", "")
    return LandingPage(
        occasion=occasion,
        color=color.lower() if HEX_COLOR.fullmatch(color) else None,
        palette=_palette(parser.styles),
        entry_module=_entry_module(parser.scripts),
    )


def _constant(module: str, name: str) -> str | None:
    """Wartosc `name="..."` z modulu (pierwsza deklaracja tej nazwy)."""
    match = re.search(rf"""(?<![\w$.]){re.escape(name)}\s*=\s*(["'])([^"'\\]*)\1""", module)
    return match.group(2) if match else None


def _facade_value(module: str, start: int) -> dict[str, str | None] | None:
    """Wartosc po `facade:` jako {jezyk: sciezka}; None, gdy ksztalt nieznany."""
    if match := _STRING_VALUE.match(module, start):
        return {lang: match.group(2) for lang in LANGUAGES}
    if match := _OBJECT_VALUE.match(module, start):
        # tylko klucze jezykow: najwyzej dwa przeszukania modulu, ile by par nie bylo
        pairs = {key: (literal, ident) for key, _quote, literal, ident in _OBJECT_PAIR.findall(match.group(1))}
        values: dict[str, str | None] = {}
        for lang in LANGUAGES:
            if lang in pairs:
                literal, ident = pairs[lang]
                values[lang] = literal if not ident else _constant(module, ident)
        return values
    if match := _IDENT_VALUE.match(module, start):
        path = _constant(module, match.group(0))
        return {lang: path for lang in LANGUAGES}
    return None


def parse_facade_paths(module: str, occasion: str) -> FacadePaths | None:
    """Sciezki fasady (pl, en) z modulu wejsciowego danej okazji.

    Modul innej okazji, nieznany zapis albo sciezka spoza /assets/*.svg daje
    None - czat pokaze wtedy kolory okazji bez fasady.
    """
    marker = re.search(rf"""\boccasion\s*:\s*(["']){re.escape(occasion)}\1""", module)
    if marker is None:
        return None
    key = _FACADE_KEY.search(module, marker.end())
    if key is None:
        return None
    values = _facade_value(module, key.end())
    if values is None:
        return None
    paths = {
        lang: path for lang in LANGUAGES
        if (path := values.get(lang)) is not None and SVG_PATH.fullmatch(path)
    }
    if not paths:
        return None
    # grafika tylko w jednym jezyku sluzy obu
    return FacadePaths(pl=paths.get("pl") or paths["en"], en=paths.get("en") or paths["pl"])
