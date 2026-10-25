"""Strony informacyjne USOSweb (menu "DOKUMENTY" i Kontakt) jako rekordy `page`.

Liste stron Dokumentow bierzemy z linkow strony glownej (panel=DOMYSLNY,
file=<nazwa>.html), a gdy nie uda sie jej ustalic - z listy zapasowej.
Pomijamy strony wymagajace logowania (dla_stud/*, dla_prac/*, dodatki/*),
deklaracje dostepnosci, mape serwisu i strone o funduszach UE, a takze
"Rejestracje zetonowe" - to aplikacja w JavaScripcie bez tresci w HTML-u
(terminy rejestracji zbiera kolektor registrations z USOS API) - i archiwum
aktualnosci (SKIPPED_FILES).
Notka "ostatnia migracja danych" nie trafia do zbioru - backend pobiera ja
na biezaco (web.parse_last_migration).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from src.backend.rag.sources.usos.dataset import PageAttributes, PageRecord

from ...common.markdown import html_to_markdown
from ..context import Context
from ..web import BASE_URL, HOST, UsosWeb, UsosWebError, is_usosweb_url, main_content, parse_last_modified

logger = logging.getLogger("usos")

NAME = "pages"
NEEDS_CONSUMER = False

HOME_URL = f"{BASE_URL}?_action=news/default"
KONTAKT_URL = f"{BASE_URL}?_action=news/kontakt"
DOCUMENTS_ACTION = "news/default"
DOCUMENTS_PANEL = "DOMYSLNY"
DOCUMENTS_LABEL = "Dokumenty"
# gdy strona glowna nie da sie pobrac albo nie ma w niej linkow (zmiana ukladu)
FALLBACK_DOCUMENTS: tuple[tuple[str, str], ...] = (
    ("index.html", "strona główna"),
    ("legitymacje.html", "legitymacje"),
    ("legitymacje_dr.html", "legitymacje doktoranckie"),
    ("mlegitymacja.html", "mLegitymacja"),
    ("pierwsze-kroki.html", "pierwsze kroki"),
    ("ankiety.html", "ankiety"),
    ("zintegruj.html", "ZintegrUJ"),
)
# strony Dokumentow pomijane mimo linku w menu: newsy.html to statyczne
# archiwum aktualnosci (2020-2026) - dubluje kolektor news i trzyma
# nieaktualne ogloszenia
SKIPPED_FILES = frozenset({"newsy.html"})
# tresc krotsza niz tyle znakow (bez tytulu) to nie strona informacyjna
MIN_CONTENT_CHARS = 200
_FILE_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.html$")
# odpowiada wyrazeniu naglowka z src/backend/rag/core/chunking.py
_HEADING = re.compile(r"^(#{1,6}) +(.+)$")


@dataclass(frozen=True)
class PageLink:
    url: str
    label: str
    breadcrumbs: tuple[str, ...]


def documents_url(file_name: str) -> str:
    """Kanoniczny adres strony Dokumentow (bez sesji, kotwic i innych parametrow)."""
    return f"{BASE_URL}?{urlencode({'_action': DOCUMENTS_ACTION, 'panel': DOCUMENTS_PANEL, 'file': file_name}, safe='/')}"


def _document_file(href: str, base_url: str) -> str | None:
    url = urljoin(base_url, href.strip())
    if not is_usosweb_url(url) or urlsplit(url).path != "/kontroler.php":
        return None
    query = parse_qs(urlsplit(url).query)
    if query.get("_action") != [DOCUMENTS_ACTION]:
        return None
    files = query.get("file") or []
    if len(files) != 1 or not _FILE_NAME.match(files[0]):
        return None
    panel = query.get("panel")
    if panel not in (None, [DOCUMENTS_PANEL]):
        return None
    return files[0]


def discover_documents(html: str, base_url: str = HOME_URL) -> list[PageLink]:
    """Strony Dokumentow z linkow strony (menu boczne najpierw - stamtad sa
    nazwy), w kolejnosci wystapienia, bez powtorzen."""
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select("menu-left a[href]") + soup.find_all("a", href=True)
    found: dict[str, str] = {}
    for anchor in anchors:
        name = _document_file(anchor["href"], base_url)
        if name is None or name in SKIPPED_FILES:
            continue
        label = " ".join(anchor.get_text(" ").split())
        if name not in found or (not found[name] and label):
            found[name] = label
    links = []
    for name, label in found.items():
        label = label or name.removesuffix(".html")
        links.append(PageLink(documents_url(name), label, (DOCUMENTS_LABEL, _label(label))))
    return links


def _label(text: str) -> str:
    """"pierwsze kroki" -> "Pierwsze kroki"; "mLegitymacja" bez zmian."""
    text = text.strip()
    if len(text) > 1 and text[0].islower() and not text[1].isupper():
        return text[0].upper() + text[1:]
    return text


def _fallback() -> list[PageLink]:
    return [PageLink(documents_url(name), label, (DOCUMENTS_LABEL, _label(label))) for name, label in FALLBACK_DOCUMENTS]


def page_links(web: UsosWeb, ctx: Context) -> list[PageLink]:
    try:
        links = discover_documents(web.get(HOME_URL))
    except UsosWebError as error:
        ctx.warn(f"pages: strona glowna USOSweb niedostepna ({error}) - lista zapasowa Dokumentow")
        links = []
    else:
        if not links:
            ctx.warn("pages: brak linkow do Dokumentow na stronie glownej USOSweb - lista zapasowa")
    links = links or _fallback()
    return [*links, PageLink(KONTAKT_URL, "Kontakt", ("Kontakt",))]


def build_record(link: PageLink, html: str, now: datetime) -> PageRecord | None:
    """Rekord strony; None, gdy strona nie ma obszaru tresci albo tresc jest
    pusta/zbyt krotka."""
    content_html = main_content(html)
    if content_html is None:
        raise UsosWebError(f"{link.url}: brak obszaru tresci (zmiana ukladu USOSweb?)")
    markdown = html_to_markdown(content_html, base_url=link.url)
    title, body = _split_title(markdown, link)
    if len(body) < MIN_CONTENT_CHARS:
        return None
    return PageRecord(
        id=link.url,
        kind="page",
        url=link.url,
        title=title,
        lang="pl",
        updated_at=parse_last_modified(html, now),
        content=f"# {title}\n\n{body}\n",
        attributes=PageAttributes(site=HOST, section="usosweb", breadcrumbs=list(link.breadcrumbs)),
    )


def _split_title(markdown: str, link: PageLink) -> tuple[str, str]:
    """Tytul strony i tresc pod nim (naglowki przesuniete tak, by byly ponizej #).

    Tytulem jest pierwszy blok, gdy to h1 albo jedyny h2 na stronie; inaczej
    nazwa z menu ("Legitymacje doktoranckie" - linia kontekstu zbioru i tak
    zaczyna sie od "USOSweb")."""
    blocks = markdown.split("\n\n")
    headings = [_HEADING.match(line) for line in markdown.split("\n")]
    levels = [len(m.group(1)) for m in headings if m]
    first = _HEADING.match(blocks[0]) if blocks and "\n" not in blocks[0] else None
    title = ""
    if first and (len(first.group(1)) == 1 or (len(first.group(1)) == 2 and levels.count(2) == 1 and 1 not in levels)):
        title = first.group(2).strip().rstrip(".").strip()
        blocks = blocks[1:]
        levels = levels[1:]
    if not title:
        title = link.breadcrumbs[-1] or link.label
    body = "\n\n".join(blocks).strip()
    if 1 in levels:
        body = "\n".join(re.sub(r"^(#{1,5}) ", r"#\1 ", line) for line in body.split("\n"))
    return title, body


def collect(ctx: Context, web: UsosWeb | None = None, now: datetime | None = None) -> Iterator[PageRecord]:
    """Rekordy stron; klient USOSweb z argumentu, z ctx.web albo nowy."""
    web = web or getattr(ctx, "web", None) or UsosWeb()
    now = now or datetime.now(ctx.tz)
    fetched = 0
    produced = 0
    for link in page_links(web, ctx):
        try:
            html = web.get(link.url)
            fetched += 1
            record = build_record(link, html, now)
        except UsosWebError as error:
            ctx.warn(f"pages: {link.url}: {error}")
            continue
        if record is None:
            logger.info("pages: %s - pusta albo zbyt krotka tresc, pomijam", link.url)
            continue
        produced += 1
        yield record
    if not fetched:
        raise UsosWebError("pages: nie udalo sie pobrac zadnej strony USOSweb")
    if not produced:
        raise UsosWebError("pages: zadna strona USOSweb nie dala tresci (zmiana ukladu?)")
