"""Rozpoznawanie rodzaju pliku po zawartosci i bezpieczna nazwa do wyswietlenia.

Rodzaj zalezy wylacznie od bajtow pliku (magic bytes) - nie od rozszerzenia
ani od Content-Type wyslanego przez przegladarke:

- PDF: zaczyna sie od "%PDF-",
- PNG: 8-bajtowa sygnatura PNG,
- JPEG: FF D8 FF,
- WEBP: "RIFF" + 4 bajty dlugosci + "WEBP",
- DOCX: archiwum zip zawierajace word/document.xml,
- TXT: poprawny UTF-8 bez bajtow NUL (wszystko inne odrzucamy).
"""

from __future__ import annotations

import codecs
import os
import re
import struct
import unicodedata
import zipfile
from pathlib import Path
from typing import Final

from ..limits.settings import ATTACHMENT_TYPES, AttachmentType

PDF_MAGIC: Final = b"%PDF-"
PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC: Final = b"\xff\xd8\xff"
ZIP_MAGIC: Final = b"PK\x03\x04"
DOCX_MAIN_PART: Final = "word/document.xml"

# Limit wpisow archiwum DOCX (zwykly dokument ma kilkanascie-kilkadziesiat).
MAX_ZIP_ENTRIES = 1000
# rekord konca spisu tresci (EOCD): sygnatura, 4 x H, 2 x L, dlugosc komentarza
_EOCD_SIGNATURE: Final = b"PK\x05\x06"
_EOCD_FORMAT: Final = "<4s4H2LH"
_EOCD_SIZE: Final = 22
_MAX_ZIP_COMMENT: Final = 0xFFFF
_ZIP64_MARKER: Final = 0xFFFF
# wpis spisu tresci to 46 B + nazwa i pola dodatkowe; z zapasem na dlugie nazwy
_MAX_DIRECTORY_BYTES_PER_ENTRY: Final = 1024

# tyle bajtow z poczatku wystarcza do rozpoznania wszystkich rodzajow binarnych
HEAD_BYTES: Final = 16
# plik tekstowy czytamy w kawalkach (wielobajtowe znaki UTF-8 na granicy kawalkow
# obsluguje dekoder przyrostowy)
_TEXT_CHUNK: Final = 64 * 1024

MAX_NAME_LENGTH: Final = 120
DEFAULT_STEM: Final = "plik"

# Typ MIME, z jakim plik jest pobierany (GET /attachments/{id}) i opisywany modelowi
MIME_TYPES: Final[dict[AttachmentType, str]] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain; charset=utf-8",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
IMAGE_KINDS: Final[frozenset[AttachmentType]] = frozenset({"png", "jpeg", "webp"})


def _end_of_central_directory(path: Path) -> tuple[int, int] | None:
    """(liczba wpisow, rozmiar spisu tresci w bajtach) z rekordu EOCD na koncu
    archiwum - bez wczytywania spisu tresci. None: brak rekordu albo ZIP64
    (dokument Worda go nie potrzebuje)."""
    size = path.stat().st_size
    tail_length = min(size, _EOCD_SIZE + _MAX_ZIP_COMMENT)
    with path.open("rb") as handle:
        handle.seek(size - tail_length)
        tail = handle.read(tail_length)
    position = tail.rfind(_EOCD_SIGNATURE)
    if position < 0 or len(tail) - position < _EOCD_SIZE:
        return None
    _, _, _, on_disk, total, directory_size, _, _ = struct.unpack(
        _EOCD_FORMAT, tail[position:position + _EOCD_SIZE]
    )
    if _ZIP64_MARKER in (on_disk, total) or directory_size == 0xFFFFFFFF:
        return None
    return max(on_disk, total), directory_size


def zip_entry_count(path: Path) -> int | None:
    """Liczba wpisow archiwum wg rekordu EOCD (None = nie da sie odczytac)."""
    directory = _end_of_central_directory(path)
    return directory[0] if directory is not None else None


def small_zip_directory(path: Path, max_entries: int) -> bool:
    """Czy spis tresci archiwum jest maly - sprawdzane PRZED zipfile.ZipFile,
    ktory wczytuje caly spis (miliony wpisow w kilku MB pliku to "bomba
    spisu tresci"). Limitujemy liczbe wpisow i rozmiar spisu, bo ZipFile
    czyta spis po rozmiarze, a nie po zadeklarowanej liczbie wpisow."""
    try:
        directory = _end_of_central_directory(path)
    except OSError:
        return False
    if directory is None:
        return False
    entries, directory_size = directory
    return entries <= max_entries and directory_size <= max_entries * _MAX_DIRECTORY_BYTES_PER_ENTRY


def _is_docx(path: Path) -> bool:
    if not small_zip_directory(path, MAX_ZIP_ENTRIES):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            # tylko spis tresci archiwum - bez rozpakowywania
            archive.getinfo(DOCX_MAIN_PART)
            return True
    except (KeyError, zipfile.BadZipFile, OSError, ValueError):
        return False


def _is_utf8_text(path: Path) -> bool:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    seen_any = False
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_TEXT_CHUNK):
                if b"\x00" in chunk:
                    return False
                decoder.decode(chunk)
                seen_any = True
            decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return seen_any


def detect_kind(path: Path) -> AttachmentType | None:
    """Rodzaj pliku po zawartosci; None = nieobslugiwany (albo pusty) plik."""
    with path.open("rb") as handle:
        head = handle.read(HEAD_BYTES)
    if not head:
        return None
    if head.startswith(PDF_MAGIC):
        return "pdf"
    if head.startswith(PNG_MAGIC):
        return "png"
    if head.startswith(JPEG_MAGIC):
        return "jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(ZIP_MAGIC):
        return "docx" if _is_docx(path) else None
    return "txt" if _is_utf8_text(path) else None


def _clean(raw: str) -> str:
    """Ostatni czlon sciezki (takze windowsowej), bez znakow sterujacych
    i niewidocznych, z pojedynczymi spacjami, bez kropek/spacji na brzegach."""
    base = raw.replace("\\", "/").rsplit("/", 1)[-1]
    kept = "".join(
        ch for ch in unicodedata.normalize("NFC", base)
        if unicodedata.category(ch)[0] != "C"
    )
    return re.sub(r"\s+", " ", kept).strip(" .")


def display_name(raw: str | None, kind: AttachmentType) -> str:
    """Bezpieczna nazwa do wyswietlenia i naglowka Content-Disposition.

    Rozszerzenie niezgodne z rozpoznanym rodzajem dostaje dopisane wlasciwe
    ("strona.html" z trescia tekstowa -> "strona.html.txt"), zeby pobrany
    plik nie otworzyl sie jako cos innego niz jest. Dlugosc najwyzej
    MAX_NAME_LENGTH znakow, z zachowaniem rozszerzenia.
    """
    name = _clean(raw or "")
    extensions = ATTACHMENT_TYPES[kind][1]
    stem, extension = os.path.splitext(name)
    if not stem:
        name, stem, extension = "", DEFAULT_STEM, ""
    if extension.lower() not in extensions:
        stem, extension = (name or stem), extensions[0]
    room = MAX_NAME_LENGTH - len(extension)
    return stem[:room].rstrip(" .") + extension
