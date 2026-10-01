"""
Konwersja danych z pipeline/scrapers/strony/scraper.py do wspolnego schematu Document.

Scraper zapisuje wszystkie strony, pliki (pdf/docx/txt) i Wikipedie do
jednego pliku data/strony/website_data.txt w formacie powtorzonym dla kazdej
strony:
    \\n\\nURL: <adres>\\n\\n<tresc strony>
Plik jest dzielony po znaczniku "URL: ", a kazda strona na chunki
(chunking.py). Zrodlo zawiera tylko tekst, wiec nie powstaja dokumenty "image".
"""

import os
import re
from urllib.parse import urlparse

from src.backend.rag.schema import Document, make_id

from .chunking import make_splitter

OUTPUT_FILE = os.path.join("data", "strony", "website_data.txt")
# Nazwa uzywana przez starsze wersje scrapera (istniejace wolumeny z danymi).
LEGACY_OUTPUT_FILE = os.path.join("data", "strony", "webiste_data.txt")

PAGE_SPLIT_PATTERN = re.compile(r"\n\nURL: (\S+)\n\n")


def _parse_pages(raw_text: str) -> list[tuple[str, str]]:
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


def _default_output_file() -> str:
    if not os.path.exists(OUTPUT_FILE) and os.path.exists(LEGACY_OUTPUT_FILE):
        return LEGACY_OUTPUT_FILE
    return OUTPUT_FILE


def load_documents(output_file: str | None = None) -> list[Document]:
    """Wczytuje i normalizuje dane ze scrapera stron do listy Document.

    Domyslnie czyta website_data.txt, a gdy go brak - starsza nazwe
    webiste_data.txt. Brak pliku daje pusta liste.
    """
    path = output_file or _default_output_file()
    if not os.path.exists(path):
        print(f"[strony] Plik {path} nie istnieje, pomijam.")
        return []

    with open(path, "r", encoding="utf-8") as f:
        pages = _parse_pages(f.read())

    splitter = make_splitter()
    documents: list[Document] = []
    for url, text in pages:
        domain = urlparse(url).netloc
        for index, chunk in enumerate(splitter.split_text(text)):
            documents.append(
                Document(
                    id=make_id("strony", url, str(index)),
                    source="strony",
                    embed_text=chunk,
                    content_type="text",
                    value=chunk,
                    metadata={"url": url, "domain": domain, "chunk_index": index},
                )
            )

    return documents
