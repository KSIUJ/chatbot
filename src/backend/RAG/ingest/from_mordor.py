"""
Konwersja danych z src/data/mordor/ do wspolnego schematu Document.

ZALOZENIA (do zweryfikowania, patrz PR):
- src/data/mordor/mordor_scraper.py w obecnym stanie NIE zapisuje wygenerowanych
  chunkow nigdzie (jest tam "# TODO : Save chunks to a database or file for
  later use") i przetwarza tylko pierwsze 5 plikow (kod testowy: files[:5]).
  Nie modyfikujemy tego pliku (zgodnie z zasada "tylko czytaj z tego modulu"),
  wiec ten modul NIE importuje scrape_mordor() - zamiast tego samodzielnie
  przechodzi po data/mordor/ i chunkuje WSZYSTKIE pliki, uzywajac dokladnie
  tego samego podejscia (pymupdf4llm.to_markdown + RecursiveCharacterTextSplitter,
  te same chunk_size/chunk_overlap) i tych samych kluczy metadanych
  (source_file, file_type, directory), zeby latwo bylo przelaczyc sie na
  wczytywanie zapisanych chunkow, gdy mordor_scraper.py zostanie dokonczony.
- src/data/mordor/files_downloader.py pobiera oprocz pdf/docx/txt takze obrazy
  (.jpg/.jpeg/.png - np. skany, plany, zdjecia notatek). Te pliki nie da sie
  sensownie zamienic na tekst przez pymupdf4llm, wiec traktujemy je jako
  osobne dokumenty typu "image" (content_type="image", value=sciezka do pliku),
  z embed_text zbudowanym z nazwy pliku i katalogu nadrzednego (jedyny dostepny
  kontekst tekstowy) - to prowizorka do czasu, az ktos doda realne opisy/OCR.
"""

import os

from ..ingest.schema import Document, make_id

BASE_DIR = os.path.join("data", "mordor")

TEXT_EXTENSIONS = {".pdf", ".docx", ".txt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def _iter_files(directory):
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.startswith("."):
                continue
            yield os.path.join(root, filename)


def _text_documents(file_path: str) -> list[Document]:
    import pymupdf4llm
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    file_name = os.path.basename(file_path)
    parent_dir = os.path.dirname(file_path)
    _, file_extension = os.path.splitext(file_name)

    try:
        clean_text = pymupdf4llm.to_markdown(file_path)
    except Exception as e:
        print(f"[mordor] Blad przetwarzania pliku {file_name}: {e}")
        return []

    if not clean_text:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    chunks = splitter.split_text(clean_text)

    documents = []
    for index, chunk in enumerate(chunks):
        metadata = {
            "source_file": file_name,
            "file_type": file_extension,
            "directory": parent_dir,
            "chunk_index": index,
        }
        documents.append(
            Document(
                id=make_id("mordor", file_path, str(index)),
                source="mordor",
                embed_text=chunk,
                content_type="text",
                value=chunk,
                metadata=metadata,
            )
        )
    return documents


def _image_document(file_path: str) -> Document:
    file_name = os.path.basename(file_path)
    parent_dir = os.path.dirname(file_path)
    category = os.path.basename(parent_dir)
    embed_text = f"{category} {file_name}".replace("_", " ").replace("-", " ")

    return Document(
        id=make_id("mordor", file_path),
        source="mordor",
        embed_text=embed_text,
        content_type="image",
        value=file_path,
        metadata={"file_name": file_name, "directory": parent_dir},
    )


def load_documents(directory: str = BASE_DIR) -> list[Document]:
    """Wczytuje i normalizuje wszystkie pliki z data/mordor/ do listy Document."""
    if not os.path.exists(directory):
        print(f"[mordor] Katalog {directory} nie istnieje, pomijam.")
        return []

    documents: list[Document] = []
    for file_path in _iter_files(directory):
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        if ext in TEXT_EXTENSIONS:
            documents.extend(_text_documents(file_path))
        elif ext in IMAGE_EXTENSIONS:
            documents.append(_image_document(file_path))
        else:
            continue

    return documents
