"""
Adapter starego wyjscia crawlera stron (pipeline/scrapers/strony/scraper.py)
do formatu uj_pages - do czasu przebudowy scrapera.

Stary crawler zapisuje wszystkie strony, pliki (pdf/docx/txt) i Wikipedie do
jednego pliku data/strony/website_data.txt w formacie powtorzonym dla kazdej
strony:
    \\n\\nURL: <adres>\\n\\n<tresc strony>
Nie ma tytulow, menu ani dat - tytul i okruszki sa wyprowadzane z adresu
(titles.py), data zostaje pusta. Rodzaj witryny (category) wynika z domeny,
typ pliku z rozszerzenia w adresie.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .dataset import PageAttributes, PageCategory, PageRecord
from .titles import Vocabulary, page_title

LEGACY_DIR = "strony"
OUTPUT_FILE = "website_data.txt"
# Nazwa uzywana przez starsze wersje scrapera (istniejace wolumeny z danymi).
LEGACY_OUTPUT_FILE = "webiste_data.txt"

PAGE_SPLIT_PATTERN = re.compile(r"\n\nURL: (\S+)\n\n")

CATEGORY_BY_HOST: dict[str, PageCategory] = {
    "matinf.uj.edu.pl": "faculty",
    "usosownia.uj.edu.pl": "usosownia",
    "kmsuj.matinf.uj.edu.pl": "student_group",
    "knmf.im.uj.edu.pl": "student_group",
    "nkr.si": "student_group",
    "pl.wikipedia.org": "wikipedia",
}

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
}


def parse_pages(raw_text: str) -> list[tuple[str, str]]:
    """Rozbija plik wyjsciowy scrapera na liste (url, tresc_strony)."""
    # re.split z grupa przechwytujaca: [prefix, url_1, text_1, url_2, text_2, ...]
    parts = PAGE_SPLIT_PATTERN.split(raw_text)
    pages = []
    for i in range(1, len(parts), 2):
        url = parts[i]
        text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if text:
            pages.append((url, text))
    return pages


def category_of(host: str) -> PageCategory:
    if host in CATEGORY_BY_HOST:
        return CATEGORY_BY_HOST[host]
    return "uj" if host == "uj.edu.pl" or host.endswith(".uj.edu.pl") else "other"


def _media_type(path: str) -> str | None:
    """Typ pliku z rozszerzenia ktoregos segmentu sciezki (Liferay dokleja
    do adresu pliku uuid: /documents/.../plik.pdf/<uuid>)."""
    for segment in unquote(path).split("/"):
        media_type = MEDIA_TYPES.get(posixpath.splitext(segment)[1].lower())
        if media_type:
            return media_type
    return None


def _lang(path: str) -> str:
    segments = [s.lower() for s in path.split("/")]
    return "en" if "en" in segments or "en-gb" in segments else "pl"


def to_record(url: str, text: str, vocabulary: Vocabulary | None = None) -> PageRecord:
    """Rekord strony; vocabulary - slownik do odtwarzania polskich znakow
    w tytule z adresu (domyslnie ze slow tej strony)."""
    parts = urlsplit(url)
    media_type = _media_type(parts.path)
    is_document = media_type is not None or parts.path.startswith("/documents/")
    category = category_of(parts.netloc)
    title = page_title(url, text, category, is_document, vocabulary or Vocabulary([text]))
    return PageRecord(
        id=url,
        kind="document" if is_document else "page",
        title=title.title,
        url=url,
        lang=_lang(parts.path),
        content=text,
        attributes=PageAttributes(
            site=parts.netloc,
            category=category,
            breadcrumbs=title.breadcrumbs,
            media_type=media_type or ("application/octet-stream" if is_document else "text/html"),
        ),
    )


def legacy_file(data_dir: Path) -> Path | None:
    directory = data_dir / LEGACY_DIR
    for name in (OUTPUT_FILE, LEGACY_OUTPUT_FILE):
        if (directory / name).is_file():
            return directory / name
    return None


def convert(data_dir: Path) -> list[PageRecord] | None:
    """Rekordy z data/strony/website_data.txt (albo starszej nazwy); None = brak pliku.
    Adres wystepujacy kilka razy - zostaje ostatnia tresc (jak przy dawnym
    nadpisywaniu w indeksie)."""
    path = legacy_file(data_dir)
    if path is None:
        return None
    pages = dict(parse_pages(path.read_text(encoding="utf-8")))
    vocabulary = Vocabulary(pages.values())
    return [to_record(url, text, vocabulary) for url, text in pages.items()]
