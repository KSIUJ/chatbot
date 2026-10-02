"""Wyciaganie tekstu z zalacznika - raz, przy wysylaniu pliku.

- PDF: PyMuPDF w OSOBNYM PROCESIE (pdf_worker.py); strony-skany sa
  rozpoznawane OCR-em (Tesseract w MuPDF), gdy sa dane jezykowe pol i eng
  (find_tessdata) - wtedy dluzsze limity czasu. Twardy limit czasu
  PDF_HARD_TIMEOUT_SECONDS (po nim proces jest zabijany) i na Linuksie
  limitem pamieci - zlosliwy PDF nie zawiesi jedynego workera uvicorna.
  Najwyzej MAX_PDF_PAGES stron i PDF_TIME_BUDGET_SECONDS sekund czytania;
  zaszyfrowany, uszkodzony albo zbyt wolny plik -> UnreadableFile.
- DOCX: word/document.xml czytany wprost z archiwum zip (bez nowej
  zaleznosci). Oslona przed zip bombami: rozmiar spisu tresci sprawdzany
  przed jego wczytaniem, limit rozmiaru po rozpakowaniu (deklarowanego
  i faktycznie przeczytanego). Tekst wyciaga wyrazenie regularne, ktore
  dziala liniowo (klasy znakow koncza sie na nastepnym "<"), a nie parser
  XML - encje z DTD ("billion laughs") nigdy nie sa rozwijane.
- TXT: UTF-8 (rodzaj sprawdzil juz sniff.py).
- Obrazy: bez tekstu - model dostaje je jako obraz (jesli dostawca umie).

Tekst jest obcinany do MAX_EXTRACTED_CHARS znakow z dopiskiem TRUNCATION_NOTE.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..limits.settings import AttachmentType
from .sniff import DOCX_MAIN_PART, IMAGE_KINDS, small_zip_directory

logger = logging.getLogger(__name__)

MAX_EXTRACTED_CHARS = 60_000
TRUNCATION_NOTE: Final = "[ucięto]"
MAX_PDF_PAGES = 100
# Limit czasu czytania stron (sprawdzany miedzy stronami, w procesie potomnym)
PDF_TIME_BUDGET_SECONDS = 20.0
# Twardy limit calego procesu potomnego (start + import + czytanie); po nim kill
PDF_HARD_TIMEOUT_SECONDS = 40.0
# Limit pamieci procesu potomnego (tylko Linux, RLIMIT_AS)
PDF_MEMORY_LIMIT_MB = 1024
PDF_WORKER_SCRIPT: Path = Path(__file__).with_name("pdf_worker.py")
PYTHON_EXECUTABLE: str = sys.executable
# Limit bajtow wyjscia procesu: JSON z tekstem obcietym do MAX_EXTRACTED_CHARS
# (UTF-8 do 4 B na znak, escapowanie do 6 B) z zapasem na reszte pol
PDF_WORKER_MAX_OUTPUT_BYTES = MAX_EXTRACTED_CHARS * 6 + 64 * 1024
# Zmienne srodowiska przekazywane procesowi PDF (reszta, w tym sekrety, nie)
_WORKER_ENV_KEEP: Final = ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP")

# OCR skanow (Tesseract wbudowany w MuPDF): potrzebne dane jezykowe pol i eng.
# Katalog z TESSDATA_PREFIX albo standardowe miejsca pakietow Debiana.
OCR_LANGUAGES: Final = ("pol", "eng")
TESSDATA_CANDIDATES: tuple[str, ...] = (
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tessdata",
)
# najwyzej tyle stron OCR na plik (OCR strony to ~1-3 s CPU)
MAX_OCR_PAGES = 20
# dluzsze limity dla sciezki z OCR (budzet czytania i twardy kill)
PDF_OCR_TIME_BUDGET_SECONDS = 100.0
PDF_OCR_HARD_TIMEOUT_SECONDS = 120.0
_ocr_unavailable_logged = False
MAX_DOCX_ENTRIES = 1000
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024

# Fragment tekstu, tabulator / lamanie linii i koniec akapitu w word/document.xml.
# Zadna klasa znakow nie przechodzi przez "<", wiec kazda proba dopasowania
# konczy sie najpozniej na nastepnym znaczniku - czas liniowy (bez ReDoS).
_DOCX_TOKEN = re.compile(r"<w:t(?:\s[^<>]*)?>([^<]*)</w:t>|<w:(tab|br|cr)\s*/>|</w:p>")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")


class UnreadableFile(ValueError):
    """Pliku nie da sie odczytac (zaszyfrowany, uszkodzony, zip bomba,
    za wolny) - wina pliku, odpowiedz 422."""


class ExtractionFailed(RuntimeError):
    """Blad po stronie serwera (np. nie da sie uruchomic procesu) - 500."""


@dataclass(frozen=True)
class Extraction:
    # None dla obrazow; "" gdy dokument nie ma tekstu (np. skan)
    text: str | None
    # liczba stron PDF (wszystkich, nie tylko odczytanych)
    pages: int | None = None
    # tekst (czesciowo) rozpoznany OCR-em ze skanu
    ocr: bool = False


def _normalized(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    joined = "\n".join(line.rstrip() for line in lines)
    return _MANY_BLANK_LINES.sub("\n\n", joined).strip()


def _capped(text: str, truncated: bool = False) -> str:
    """Tekst po normalizacji, najwyzej MAX_EXTRACTED_CHARS znakow; obciety
    (tu albo wczesniej - truncated) konczy sie TRUNCATION_NOTE."""
    clean = _normalized(text)
    if len(clean) > MAX_EXTRACTED_CHARS:
        clean, truncated = clean[:MAX_EXTRACTED_CHARS].rstrip(), True
    return f"{clean}\n{TRUNCATION_NOTE}" if truncated else clean


# --- PDF (osobny proces) -------------------------------------------------------------

def _has_ocr_languages(directory: Path) -> bool:
    return all((directory / f"{language}.traineddata").is_file() for language in OCR_LANGUAGES)


def find_tessdata() -> Path | None:
    """Katalog danych Tesseracta z jezykami pol i eng (TESSDATA_PREFIX albo
    TESSDATA_CANDIDATES); None = OCR niedostepny (np. lokalnie na Windows)."""
    env_dir = os.getenv("TESSDATA_PREFIX", "").strip()
    for candidate in (env_dir, *TESSDATA_CANDIDATES):
        if candidate and _has_ocr_languages(Path(candidate)):
            return Path(candidate)
    return None


def _worker_timeout(tessdata: Path | None) -> float:
    return PDF_OCR_HARD_TIMEOUT_SECONDS if tessdata is not None else PDF_HARD_TIMEOUT_SECONDS


def _worker_env(tessdata: Path | None) -> dict[str, str]:
    """Minimalne srodowisko procesu potomnego - bez kluczy API, DATABASE_URL
    i sekretow OIDC. SYSTEMROOT jest potrzebny Pythonowi na Windows,
    TESSDATA_PREFIX - OCR-owi."""
    env = {name: os.environ[name] for name in _WORKER_ENV_KEEP if name in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    if tessdata is not None:
        env["TESSDATA_PREFIX"] = str(tessdata)
    return env


def _read_capped(process: subprocess.Popen[bytes], limit: int) -> bytes:
    """Czyta stdout procesu, najwyzej limit + 1 bajtow; po przekroczeniu
    limitu zabija proces (inaczej zablokowalby sie na pelnym potoku)."""
    if process.stdout is None:
        raise ExtractionFailed("pdf worker has no stdout pipe")
    data = process.stdout.read(limit + 1)
    if len(data) > limit:
        process.kill()
    return data


def _run_pdf_worker(path: Path, tessdata: Path | None) -> bytes:
    """stdout procesu potomnego (najwyzej PDF_WORKER_MAX_OUTPUT_BYTES). Proces
    jest zabijany po PDF_HARD_TIMEOUT_SECONDS (z OCR: PDF_OCR_HARD_TIMEOUT_SECONDS)
    i zawsze na niego czekamy, wiec nic nie zostaje w tle."""
    budget = PDF_OCR_TIME_BUDGET_SECONDS if tessdata is not None else PDF_TIME_BUDGET_SECONDS
    command = [
        PYTHON_EXECUTABLE, "-I", str(PDF_WORKER_SCRIPT), str(path),
        str(MAX_PDF_PAGES), str(MAX_EXTRACTED_CHARS), str(budget), str(PDF_MEMORY_LIMIT_MB),
        str(tessdata) if tessdata is not None else "", str(MAX_OCR_PAGES),
    ]
    limit = PDF_WORKER_MAX_OUTPUT_BYTES
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=_worker_env(tessdata),
        )
    except OSError as exc:
        raise ExtractionFailed(f"cannot start pdf worker: {exc}") from exc
    with process:
        with ThreadPoolExecutor(max_workers=1) as reader:
            output = reader.submit(_read_capped, process, limit)
            try:
                process.wait(timeout=_worker_timeout(tessdata))
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.wait()
                raise UnreadableFile("pdf extraction timeout") from exc
            data = output.result()
    if len(data) > limit:
        raise UnreadableFile("pdf worker output too large")
    if process.returncode != 0:
        # np. przekroczony limit pamieci albo CPU - wina pliku
        raise UnreadableFile(f"pdf worker exited with {process.returncode}")
    return data


def _log_missing_ocr_once() -> None:
    global _ocr_unavailable_logged
    if not _ocr_unavailable_logged:
        _ocr_unavailable_logged = True
        logger.warning(
            "OCR unavailable (no Tesseract data for %s) - scanned PDFs get no text", "+".join(OCR_LANGUAGES)
        )


def _pdf(path: Path) -> Extraction:
    tessdata = find_tessdata()
    output = _run_pdf_worker(path, tessdata)
    try:
        result = json.loads(output)
    except ValueError as exc:
        raise UnreadableFile("pdf worker returned invalid output") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        error = result.get("error") if isinstance(result, dict) else None
        raise UnreadableFile(f"unreadable pdf: {error}")
    text, pages, truncated = result.get("text"), result.get("pages"), result.get("truncated")
    ocr = result.get("ocr", False)
    if (
        not isinstance(text, str) or not isinstance(pages, int) or not isinstance(truncated, bool)
        or not isinstance(ocr, bool)
    ):
        raise UnreadableFile("pdf worker returned malformed result")
    if tessdata is None and not text.strip():
        _log_missing_ocr_once()
    return Extraction(text=_capped(text, truncated), pages=pages, ocr=ocr)


# --- DOCX ----------------------------------------------------------------------------

def _main_part(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    """Wpis word/document.xml z kontrola rozmiaru po rozpakowaniu."""
    try:
        main = archive.getinfo(DOCX_MAIN_PART)
    except KeyError as exc:
        raise UnreadableFile("docx without word/document.xml") from exc
    if main.file_size > MAX_DOCX_XML_BYTES:
        raise UnreadableFile(f"docx document.xml too large ({main.file_size} B)")
    return main


# bledy zipfile/zlib przy uszkodzonym albo zaszyfrowanym archiwum
_ZIP_ERRORS = (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, EOFError, NotImplementedError)


def _docx_xml(path: Path) -> bytes:
    # spis tresci sprawdzany przed zipfile.ZipFile, ktory wczytuje go w calosci
    if not small_zip_directory(path, MAX_DOCX_ENTRIES):
        raise UnreadableFile("docx with too large or missing zip directory")
    try:
        with zipfile.ZipFile(path) as archive:
            main = _main_part(archive)
            with archive.open(main) as stream:
                # deklarowany rozmiar moze klamac - czytamy najwyzej limit + 1
                data = stream.read(MAX_DOCX_XML_BYTES + 1)
    except _ZIP_ERRORS as exc:
        raise UnreadableFile(f"broken docx: {exc}") from exc
    if len(data) > MAX_DOCX_XML_BYTES:
        raise UnreadableFile("docx document.xml larger than declared")
    return data


def docx_text(xml: str) -> str:
    """Tekst z word/document.xml: fragmenty w:t, tabulatory, nowe linie."""
    pieces: list[str] = []
    for match in _DOCX_TOKEN.finditer(xml):
        text, tag = match.group(1), match.group(2)
        if text is not None:
            pieces.append(html.unescape(text))
        elif tag == "tab":
            pieces.append("\t")
        else:
            pieces.append("\n")
    return "".join(pieces)


def _docx(path: Path) -> Extraction:
    xml = _docx_xml(path).decode("utf-8", errors="replace")
    return Extraction(text=_capped(docx_text(xml)))


def _txt(path: Path) -> Extraction:
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnreadableFile("text is not utf-8") from exc
    return Extraction(text=_capped(text))


def extract(path: Path, kind: AttachmentType) -> Extraction:
    """Tekst i liczba stron pliku danego rodzaju.

    Raises:
        UnreadableFile: plik zaszyfrowany, uszkodzony albo podejrzany (zip
            bomba, za wolny parser) - wina pliku.
        ExtractionFailed: blad serwera (nie da sie uruchomic procesu PDF).
    """
    if kind in IMAGE_KINDS:
        return Extraction(text=None)
    if kind == "pdf":
        return _pdf(path)
    if kind == "docx":
        return _docx(path)
    return _txt(path)
