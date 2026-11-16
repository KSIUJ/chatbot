"""
HTML -> Markdown dla scraperow (format zbiorow RAG-a: tresc w Markdownie,
naglowki dziela ja na fragmenty - src/backend/rag/DATASETS.md).

Zachowuje naglowki, akapity, listy (takze zagniezdzone), tabele, linki
(adresy wzgledne zamieniane na bezwzgledne) i pogrubienia; pomija skrypty,
style, formularze, obrazy i elementy ukryte. Wynik to czysty tekst - zadnego
HTML-a, wiec tresc ze strony nie przemyci znacznikow do kontekstu modelu.
Struktura Markdownu powstaje tylko ze struktury HTML-a: tekst wygladajacy
jak naglowek czy lista ("# ZRODLA", "1. punkt") dostaje ukosnik, a znaki
sterujace i separatory linii Unicode (U+2028 itp. - lamia odczyt JSONL)
sa usuwane.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag

DROP_TAGS = {
    "script", "style", "noscript", "template", "iframe", "object", "embed", "svg", "canvas",
    "form", "input", "button", "select", "textarea", "img", "picture", "video", "audio", "head",
}
BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "header", "footer", "aside", "nav", "blockquote",
    "address", "figure", "figcaption", "dl", "dt", "dd", "center", "fieldset",
}
HEADINGS = {f"h{n}": n for n in range(1, 7)}
# znaczniki w linii; kazdy inny (takze wlasne elementy stron, np. <usos-frame>)
# traktujemy jak blok, zeby naglowki i listy w srodku nie splaszczyly sie
INLINE_TAGS = {
    "a", "abbr", "b", "bdi", "bdo", "cite", "code", "data", "dfn", "em", "font", "i", "kbd", "label", "mark",
    "q", "s", "samp", "small", "span", "strong", "sub", "sup", "time", "u", "var", "wbr", "del", "ins", "br",
}
SAFE_SCHEMES = ("http", "https", "mailto", "tel")
_SPACES = re.compile(r"[ \t\r\f\v ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
# separatory linii spoza \n (str.splitlines dzieli po nich wiersze JSONL) i inne
# biale znaki sterujace -> spacja; pozostale znaki sterujace C0/C1 (poza \n i \t) - usuwane
_CONTROL = {ord(c): " " for c in "\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"}
_CONTROL.update({c: None for c in [*range(0x20), *range(0x7F, 0xA0)] if c not in _CONTROL and chr(c) not in "\n\t"})
# poczatek linii, ktory w Markdownie bylby struktura (naglowek, cytat, lista,
# tabela, blok kodu, linia pozioma / podkreslenie naglowka)
_STRUCTURE_START = re.compile(r"[#>|]|[-*+](?:\s|$)|[-=_*]+\s*$|```|~~~")
_NUMBERED_START = re.compile(r"(\d{1,9})([.)])(?=\s|$)")
# klasy CSS ukrywajace element (Bootstrap i podobne)
HIDDEN_CLASSES = {"d-none", "hidden", "sr-only", "visually-hidden", "invisible"}
_ZERO = re.compile(r"(?:0+(?:\.0*)?|\.0+)(?:[a-z]+|%)?")
# znaki kodowane w adresie linku, zeby nie zamknely skladni [tekst](adres)
_URL_ESCAPES = {ord(c): f"%{ord(c):02X}" for c in " ()[]<>"}
_URL_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f-\x9f]|[^\S ]")
_BACKTICKS = re.compile(r"`+")


def clean_text(text: str) -> str:
    """Tekst bez znakow sterujacych; separatory linii Unicode zamienione na spacje."""
    return text.translate(_CONTROL)


def escape_line_start(line: str) -> str:
    """Poprzedza ukosnikiem poczatek linii, ktory Markdown uznalby za strukture
    ("# ZRODLA" -> "\\# ZRODLA", "1. punkt" -> "1\\. punkt") - tekst strony nie
    moze tworzyc naglowkow ani list, ktorych nie ma w HTML-u."""
    numbered = _NUMBERED_START.match(line)
    if numbered:
        return f"{numbered.group(1)}\\{line[numbered.end(1):]}"
    if _STRUCTURE_START.match(line):
        return "\\" + line
    return line


def _escape_lines(text: str) -> str:
    return "\n".join(escape_line_start(line.strip()) for line in text.split("\n"))


def html_to_markdown(html: str, base_url: str = "", heading_offset: int = 0) -> str:
    """Markdown z fragmentu albo calej strony HTML.

    `heading_offset` przesuwa poziomy naglowkow (np. 1: h1 -> ##), zeby tresc
    pasowala pod naglowek dodany przez scraper.
    """
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "lxml")
    root = soup.body or soup
    return _finish(_Converter(base_url, heading_offset).blocks(root))


def text_of(html: str) -> str:
    """Sam tekst (jedna linia) z krotkiego fragmentu HTML, np. nazwy albo dyzurow."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    return " ".join(clean_text(soup.get_text(" ")).split())


def _finish(text: str) -> str:
    lines = [line.rstrip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def _text_node(node: NavigableString) -> str:
    # zawiniecie wiersza w zrodle to spacja; nowa linia tylko z <br>
    return clean_text(str(node)).replace("\n", " ")


def _hidden(tag: Tag) -> bool:
    if tag.has_attr("hidden") or str(tag.get("aria-hidden") or "").strip().lower() == "true":
        return True
    classes = tag.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    if HIDDEN_CLASSES & {c.lower() for c in classes}:
        return True
    return _style_hidden(str(tag.get("style") or ""))


def _style_hidden(style: str) -> bool:
    """Styl ukrywajacy element: display:none, visibility:hidden, opacity:0, font-size:0."""
    for declaration in re.sub(r"\s+", "", style).lower().split(";"):
        prop, _, value = declaration.partition(":")
        value = value.removesuffix("!important")
        if (prop, value) in (("display", "none"), ("visibility", "hidden"), ("visibility", "collapse")):
            return True
        if prop in ("opacity", "font-size") and _ZERO.fullmatch(value):
            return True
    return False


def _fenced(code: str) -> str:
    """Blok kodu w plocie dluzszym niz najdluzszy ciag ` w kodzie."""
    longest = max((len(run) for run in _BACKTICKS.findall(code)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{code}\n{fence}"


class _Converter:
    def __init__(self, base_url: str, heading_offset: int):
        self.base_url = base_url
        self.heading_offset = heading_offset

    # --- bloki -------------------------------------------------------------------------

    def blocks(self, node: Tag) -> str:
        out: list[str] = []
        inline: list[str] = []

        def flush() -> None:
            text = _escape_lines(_SPACES.sub(" ", "".join(inline)).strip())
            if text.strip():
                out.append(text)
            inline.clear()

        for child in node.children:
            if isinstance(child, NavigableString):
                if type(child) is NavigableString:  # bez komentarzy, CDATA, doctype
                    inline.append(_text_node(child))
                continue
            if not isinstance(child, Tag) or child.name in DROP_TAGS or _hidden(child):
                continue
            name = child.name
            if name in HEADINGS:
                flush()
                level = min(6, HEADINGS[name] + self.heading_offset)
                text = _SPACES.sub(" ", self.inline(child)).strip()
                if text:
                    out.append(f"{'#' * level} {text}")
            elif name in ("ul", "ol"):
                flush()
                listing = self.listing(child, 0)
                if listing:
                    out.append(listing)
            elif name == "table":
                flush()
                table = self.table(child)
                if table:
                    out.append(table)
            elif name == "pre":
                flush()
                code = clean_text(child.get_text()).strip("\n")
                if code.strip():
                    out.append(_fenced(code))
            elif name == "hr":
                flush()
            elif name == "br":
                inline.append("\n")
            elif name in BLOCK_TAGS or name == "li" or name not in INLINE_TAGS:
                flush()
                inner = self.blocks(child)
                if inner:
                    out.append(inner)
            else:
                inline.append(self.inline_tag(child))
        flush()
        return "\n\n".join(part for part in out if part.strip())

    def listing(self, node: Tag, depth: int) -> str:
        lines: list[str] = []
        ordered = node.name == "ol"
        number = 1
        for item in node.find_all("li", recursive=False):
            nested = [child for child in item.find_all(("ul", "ol"), recursive=False)]
            for child in nested:
                child.extract()
            text = _SPACES.sub(" ", self.blocks(item).replace("\n\n", " ").replace("\n", " ")).strip()
            marker = f"{number}." if ordered else "-"
            if text:
                lines.append(f"{'  ' * depth}{marker} {text}")
                number += 1
            for child in nested:
                inner = self.listing(child, depth + 1)
                if inner:
                    lines.append(inner)
        return "\n".join(lines)

    def table(self, node: Tag) -> str:
        rows: list[list[str]] = []
        for row in node.find_all("tr"):
            if row.find_parent("table") is not node:
                continue
            cells = [
                _SPACES.sub(" ", self.inline(cell).replace("\n", " ")).strip().replace("|", "\\|")
                for cell in row.find_all(("th", "td"), recursive=False)
            ]
            if any(cells):
                rows.append(cells)
        if not rows:
            return ""
        if len(rows) == 1 or max(len(r) for r in rows) == 1:
            # tabela uzyta do ukladu strony, nie do danych - zwykle akapity
            return "\n\n".join(escape_line_start(" ".join(c for c in r if c)) for r in rows)
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(lines)

    # --- tekst w linii -----------------------------------------------------------------

    def inline(self, node: Tag) -> str:
        parts: list[str] = []
        for child in node.children:
            if isinstance(child, NavigableString):
                if type(child) is NavigableString:
                    parts.append(_text_node(child))
                continue
            if isinstance(child, Tag) and child.name not in DROP_TAGS and not _hidden(child):
                parts.append(self.inline_tag(child))
        return "".join(parts)

    def inline_tag(self, tag: Tag) -> str:
        """Jeden znacznik w linii razem z jego formatowaniem (link, pogrubienie)."""
        if tag.name == "br":
            return "\n"
        if tag.name == "a":
            return self.link(tag)
        if tag.name in ("strong", "b"):
            text = self.inline(tag).strip()
            return f"**{text}**" if text else ""
        if tag.name in ("ul", "ol"):
            return " " + self.listing(tag, 0).replace("\n", " ") + " "
        if tag.name == "table":
            return " " + self.table(tag) + " "
        return self.inline(tag)

    def link(self, node: Tag) -> str:
        """Link Markdownu; adres niebezpieczny albo z bialymi znakami (poza
        spacja) i znakami sterujacymi - sam tekst."""
        text = _SPACES.sub(" ", self.inline(node)).strip()
        href = str(node.get("href") or "").strip()
        if not href or _URL_FORBIDDEN.search(href):
            return text
        url = urljoin(self.base_url, href)
        if not url or _URL_FORBIDDEN.search(url) or urlsplit(url).scheme.lower() not in SAFE_SCHEMES:
            return text
        if url.lower().startswith("mailto:"):
            # sam adres, bez ?subject=...&body=...
            address = url[len("mailto:"):].split("?", 1)[0].strip()
            if not address or address in text:
                return text
            return f"{text} ({address})".strip()
        if not text or text == url:
            return url.translate(_URL_ESCAPES)
        label = text.replace("[", "\\[").replace("]", "\\]")
        return f"[{label}]({url.translate(_URL_ESCAPES)})"
