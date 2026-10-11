"""
Adapter plikow pobranych starym skryptem (pipeline/scrapers/mordor/
files_downloader.py) do formatu mordor - do czasu przebudowy scrapera.

Pliki leza w data/mordor/ w strukturze katalogow Mordoru; rekordy sa
zapisywane obok nich. Przedmiot, rok akademicki i rodzaj materialu sa
odgadywane ze sciezki (paths.py).

- pdf z warstwa tekstu: Markdown strona po stronie (pymupdf4llm) w `pages`
  i calosc w `content`; strony bez tekstu (wklejone skany) ida do OCR
- pdf bez warstwy tekstu (skan): OCR Tesseractem wbudowanym w PyMuPDF
  (pol+eng, najwyzej MAX_OCR_PAGES stron); tekst w `pages` z `ocr: true`
  i rekord `text`. Bez danych Tesseracta albo bez tekstu z OCR - `scan`
- docx, txt: Markdown (pymupdf4llm) w `content`
- jpg, jpeg, png: `image`
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from .dataset import MaterialAttributes, MaterialRecord, Page
from .paths import parse_path

if TYPE_CHECKING:
    import pymupdf

LEGACY_DIR = "mordor"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
TEXT_EXTENSIONS = {".docx", ".txt"}
PROGRESS_EVERY = 200

# OCR: jezyki, rozdzielczosc renderowania strony, limit stron na plik i prog
# "strony bez tekstu" (jak w zalacznikach - attachments/pdf_worker.py)
OCR_LANGUAGES = "pol+eng"
OCR_DPI = 200
MAX_OCR_PAGES = 40
MIN_TEXT_LAYER_CHARS = 20
TESSDATA_CANDIDATES = (
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tessdata",
)


def find_tessdata() -> str | None:
    """Katalog danych Tesseracta z pol i eng (TESSDATA_PREFIX albo miejsca
    pakietow Debiana); None = OCR niedostepny."""
    for candidate in (os.getenv("TESSDATA_PREFIX", "").strip(), *TESSDATA_CANDIDATES):
        if candidate and all((Path(candidate) / f"{lang}.traineddata").is_file() for lang in ("pol", "eng")):
            return candidate
    return None


def _iter_files(directory: Path) -> Iterator[Path]:
    for root, _, filenames in os.walk(directory):
        for filename in sorted(filenames):
            if not filename.startswith("."):
                yield Path(root) / filename


def _pdf_has_text_layer(file_path: Path, min_chars: int = MIN_TEXT_LAYER_CHARS) -> bool:
    """Czy pdf ma co najmniej min_chars znakow tekstu; nieczytelny pdf -> False (skan)."""
    import pymupdf

    pymupdf.TOOLS.mupdf_display_errors(False)

    try:
        doc = pymupdf.open(file_path)
    except Exception:
        return False
    try:
        total = 0
        for page in doc:
            total += len(page.get_text("text").strip())
            if total >= min_chars:
                return True
        return False
    except Exception:
        return False
    finally:
        doc.close()


def _markdown(file_path: Path) -> str:
    import pymupdf4llm

    try:
        return pymupdf4llm.to_markdown(str(file_path)) or ""
    except Exception as e:
        print(f"[mordor] Blad przetwarzania pliku {file_path.name}: {e}")
        return ""


def _ocr_page(page: pymupdf.Page, tessdata: str) -> str:
    """Tekst strony z OCR; blad OCR = pusty tekst."""
    try:
        textpage = page.get_textpage_ocr(language=OCR_LANGUAGES, dpi=OCR_DPI, full=True, tessdata=tessdata)
        return str(page.get_text("text", textpage=textpage)).strip()
    except Exception as e:
        print(f"[mordor] Blad OCR strony {page.number + 1}: {e}")
        return ""


class _OcrBudget:
    """Ile stron jednego pliku mozna jeszcze rozpoznac OCR-em."""

    def __init__(self, tessdata: str | None, pages: int = MAX_OCR_PAGES) -> None:
        self.tessdata = tessdata
        self.left = pages if tessdata else 0

    def read(self, page: pymupdf.Page) -> str:
        if self.left <= 0 or self.tessdata is None:
            return ""
        self.left -= 1
        return _ocr_page(page, self.tessdata)


def _pdf_text_pages(file_path: Path, tessdata: str | None) -> list[Page]:
    """Strony pdf z warstwa tekstu (Markdown); strony prawie bez tekstu - OCR."""
    import pymupdf
    import pymupdf4llm

    try:
        chunks = pymupdf4llm.to_markdown(str(file_path), page_chunks=True)
    except Exception as e:
        print(f"[mordor] Blad przetwarzania pliku {file_path.name}: {e}")
        return []
    budget = _OcrBudget(tessdata)
    pages: list[Page] = []
    with pymupdf.open(file_path) as doc:
        for number, chunk in enumerate(chunks, start=1):
            text = (chunk.get("text") or "").strip()
            if len(text) < MIN_TEXT_LAYER_CHARS and number <= len(doc):
                ocr_text = budget.read(doc[number - 1])
                if ocr_text:
                    pages.append(Page(number=number, text=ocr_text, ocr=True))
                    continue
            if text:
                pages.append(Page(number=number, text=text))
    return pages


def _scan_pages(file_path: Path, tessdata: str | None) -> list[Page]:
    """Strony skanu odczytane OCR-em (pusto bez danych Tesseracta)."""
    if tessdata is None:
        return []
    import pymupdf

    budget = _OcrBudget(tessdata)
    pages: list[Page] = []
    try:
        with pymupdf.open(file_path) as doc:
            for page in doc:
                text = budget.read(page)
                if text:
                    pages.append(Page(number=page.number + 1, text=text, ocr=True))
    except Exception as e:
        print(f"[mordor] Blad OCR pliku {file_path.name}: {e}")
    return pages


def _record(path: str, kind: str, content: str = "", pages: list[Page] | None = None) -> MaterialRecord:
    file_type = os.path.splitext(path)[1].lower().lstrip(".")
    info = parse_path(path)
    return MaterialRecord(
        id=path,
        kind=kind,
        title=os.path.basename(path),
        content=content,
        attributes=MaterialAttributes(
            path=path,
            file_type=file_type,
            course=info.course,
            academic_year=info.academic_year,
            material_kind=info.material_kind,
            pages=pages or [],
        ),
    )


def _pages_record(path: str, pages: list[Page]) -> MaterialRecord:
    return _record(path, "text", "\n\n".join(p.text for p in pages), pages)


def pdf_record(file_path: Path, path: str, tessdata: str | None) -> MaterialRecord | None:
    """Rekord pdf: tekst strona po stronie, skan z OCR albo skan bez tekstu;
    None = pdf z warstwa tekstu, z ktorego nic nie wyszlo (pomijany jak dawniej)."""
    if _pdf_has_text_layer(file_path):
        pages = _pdf_text_pages(file_path, tessdata)
        return _pages_record(path, pages) if pages else None
    pages = _scan_pages(file_path, tessdata)
    if sum(len(p.text) for p in pages) >= MIN_TEXT_LAYER_CHARS:
        return _pages_record(path, pages)
    return _record(path, "scan")


def convert(data_dir: Path) -> list[MaterialRecord] | None:
    """Rekordy plikow z data/mordor/; None = brak katalogu. Plik tekstowy, z
    ktorego nie udalo sie wyciagnac tekstu, jest pomijany (jak dawniej)."""
    directory = data_dir / LEGACY_DIR
    if not directory.is_dir():
        return None

    import pymupdf4llm

    pymupdf4llm.use_layout(False)
    tessdata = find_tessdata()
    if tessdata is None:
        print("[mordor] brak danych Tesseracta (pol, eng) - skany bez OCR")

    records: list[MaterialRecord] = []
    processed = 0
    for file_path in _iter_files(directory):
        ext = file_path.suffix.lower()
        path = file_path.relative_to(directory).as_posix()
        if ext == ".pdf":
            record = pdf_record(file_path, path, tessdata)
            if record is not None:
                records.append(record)
        elif ext in TEXT_EXTENSIONS:
            content = _markdown(file_path)
            if content:
                records.append(_record(path, "text", content))
        elif ext in IMAGE_EXTENSIONS:
            records.append(_record(path, "image"))
        else:
            continue
        processed += 1
        if processed % PROGRESS_EVERY == 0:
            print(f"[mordor] przetworzono {processed} plikow")
    print(f"[mordor] gotowe: {processed} plikow, {len(records)} rekordow")
    return records
