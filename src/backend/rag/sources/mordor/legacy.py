"""
Adapter plikow pobranych starym skryptem (pipeline/scrapers/mordor/
files_downloader.py) do formatu mordor - do czasu przebudowy scrapera.

Pliki leza w data/mordor/ w strukturze katalogow Mordoru; rekordy sa
zapisywane obok nich. Pliki tekstowe (pdf z warstwa tekstu, docx, txt) sa
zamieniane na Markdown (pymupdf4llm), pdf bez warstwy tekstu to skan, a
.jpg/.jpeg/.png - obraz.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from .dataset import MaterialAttributes, MaterialRecord

LEGACY_DIR = "mordor"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
TEXT_EXTENSIONS = {".docx", ".txt"}
PROGRESS_EVERY = 200


def _iter_files(directory: Path) -> Iterator[Path]:
    for root, _, filenames in os.walk(directory):
        for filename in sorted(filenames):
            if not filename.startswith("."):
                yield Path(root) / filename


def _pdf_has_text_layer(file_path: Path, min_chars: int = 20) -> bool:
    """Czy pdf ma co najmniej min_chars znakow tekstu; nieczytelny pdf -> False (skan)."""
    import fitz

    fitz.TOOLS.mupdf_display_errors(False)

    try:
        doc = fitz.open(file_path)
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


def _record(path: str, kind: str, content: str = "") -> MaterialRecord:
    file_type = os.path.splitext(path)[1].lower().lstrip(".")
    return MaterialRecord(
        id=path,
        kind=kind,
        title=os.path.basename(path),
        content=content,
        attributes=MaterialAttributes(path=path, file_type=file_type),
    )


def convert(data_dir: Path) -> list[MaterialRecord] | None:
    """Rekordy plikow z data/mordor/; None = brak katalogu. Plik tekstowy, z
    ktorego nie udalo sie wyciagnac tekstu, jest pomijany (jak dawniej)."""
    directory = data_dir / LEGACY_DIR
    if not directory.is_dir():
        return None

    import pymupdf4llm

    pymupdf4llm.use_layout(False)

    records: list[MaterialRecord] = []
    processed = 0
    for file_path in _iter_files(directory):
        ext = file_path.suffix.lower()
        path = file_path.relative_to(directory).as_posix()
        if ext == ".pdf":
            if _pdf_has_text_layer(file_path):
                content = _markdown(file_path)
                if content:
                    records.append(_record(path, "text", content))
            else:
                records.append(_record(path, "scan"))
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
