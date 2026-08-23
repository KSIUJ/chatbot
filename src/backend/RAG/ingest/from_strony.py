"""
Konwersja danych z src/data/strony/scraper.py do wspolnego schematu Document.

ZALOZENIA (do zweryfikowania, patrz PR):
- scraper.py zapisuje WSZYSTKIE zescrapowane strony/pliki (pdf/docx/txt) i
  Wikipedie do jednego plaskiego pliku tekstowego
  (data/strony/webiste_data.txt - literowka "webiste" jest w oryginalnym
  kodzie, celowo jej tu nie poprawiamy), w formacie:
      \n\nURL: <adres>\n\n<tresc strony>
  powtorzonym dla kazdej strony. Sam scraper NIE dzieli tresci na chunki ani
  nie zapisuje osobnych metadanych poza URL-em (bez tytulu strony, daty itp.)
  - tutaj parsujemy ten plik po znaczniku "URL: " i dopiero dzielimy kazda
  strone na chunki (tym samym splitterem co from_mordor.py, dla spojnosci).
- scraper.py wyciaga WYLACZNIE tekst (BeautifulSoup .get_text / pypdf / docx)
  - nie zapisuje linkow do obrazow (np. map kampusu, planow budynkow), wiec
  ten modul nie generuje dokumentow typu "image" ze zrodla "strony".
- Jesli plik wyjsciowy jeszcze nie istnieje (scraper nie byl uruchamiany),
  load_documents() zwraca pusta liste zamiast rzucac wyjatkiem.
"""

import os
import re
from urllib.parse import urlparse

from ..ingest.schema import Document, make_id

OUTPUT_FILE = os.path.join("data", "strony", "webiste_data.txt")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

PAGE_SPLIT_PATTERN = re.compile(r"\n\nURL: (\S+)\n\n")


def _parse_pages(raw_text: str) -> list[tuple[str, str]]:
    """Rozbija plik wyjsciowy scrapera na liste (url, tresc_strony)."""
    parts = PAGE_SPLIT_PATTERN.split(raw_text)
    # re.split z grupa przechwytujaca zwraca: [prefix, url_1, text_1, url_2, text_2, ...]
    # prefix przed pierwszym "URL: " jest zawsze pusty (plik zaczyna sie od "\n\nURL: ")
    pages = []
    for i in range(1, len(parts), 2):
        url = parts[i]
        text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if text:
            pages.append((url, text))
    return pages


def load_documents(output_file: str = OUTPUT_FILE) -> list[Document]:
    """Wczytuje i normalizuje dane ze scrapera stron do listy Document."""
    if not os.path.exists(output_file):
        print(f"[strony] Plik {output_file} nie istnieje, pomijam.")
        return []

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    with open(output_file, "r", encoding="utf-8") as f:
        raw_text = f.read()

    pages = _parse_pages(raw_text)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )

    documents: list[Document] = []
    for url, text in pages:
        domain = urlparse(url).netloc
        chunks = splitter.split_text(text)
        for index, chunk in enumerate(chunks):
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
