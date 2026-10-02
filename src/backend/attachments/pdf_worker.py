"""Wyciaganie tekstu z PDF w osobnym procesie (uruchamiane przez extract.py).

Samodzielny skrypt - importuje tylko biblioteke standardowa i pymupdf, bez
pakietu aplikacji. Zlosliwy PDF moze zawiesic albo zjesc pamiec parsera,
dlatego proces rodzica pilnuje twardego limitu czasu (kill), limitu bajtow
wyjscia i czystego srodowiska, a tu na Linuksie ustawiamy limit pamieci
(RLIMIT_AS) i czasu CPU. Tekst jest obcinany juz tutaj (MAX_ZNAKOW).

Podczas pracy stdout (takze deskryptor 1 - komunikaty bibliotek w C) idzie
na stderr; wynik trafia na zachowany oryginalny stdout, wiec nic nie zepsuje
JSON-a.

Strony bez warstwy tekstowej (skany) sa rozpoznawane OCR-em - Tesseract
wbudowany w MuPDF, dane jezykowe pol i eng z katalogu TESSDATA - najwyzej
MAX_STRON_OCR stron na plik. Bez katalogu tessdata OCR jest pomijany.

Uzycie: pdf_worker.py SCIEZKA MAX_STRON MAX_ZNAKOW BUDZET_S LIMIT_PAMIECI_MB [TESSDATA MAX_STRON_OCR]
Wynik (stdout, jeden JSON w UTF-8):
  {"ok": true, "text": "...", "pages": N, "truncated": bool, "ocr": bool}
  {"ok": false, "error": "encrypted" | "broken" | "no_pages"}
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pymupdf

MB = 1024 * 1024
# zapas czasu CPU ponad budzet (start interpretera, import pymupdf)
CPU_SECONDS_MARGIN = 10
# OCR: jezyki Tesseracta, rozdzielczosc renderowania strony i prog "skanu" -
# strona z mniejsza liczba znakow w warstwie tekstowej idzie do OCR
OCR_LANGUAGES = "pol+eng"
OCR_DPI = 200
MIN_TEXT_LAYER_CHARS = 20
STDOUT_FD = 1
STDERR_FD = 2


def _limit_resources(memory_mb: int, budget_seconds: float) -> None:
    """Limity procesu na Linuksie; na Windows modul resource nie istnieje."""
    try:
        import resource
    except ImportError:
        return
    memory = memory_mb * MB
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    cpu = int(budget_seconds) + CPU_SECONDS_MARGIN
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))


def _ocr_text(page: pymupdf.Page, tessdata: str) -> str:
    """Tekst strony rozpoznany Tesseractem wbudowanym w MuPDF (dane jezykowe
    z katalogu tessdata)."""
    textpage = page.get_textpage_ocr(
        language=OCR_LANGUAGES, dpi=OCR_DPI, full=True, tessdata=tessdata
    )
    return str(page.get_text("text", textpage=textpage))


def _page_text(page: pymupdf.Page, ocr_allowed: bool, tessdata: str | None) -> tuple[str, bool]:
    """Tekst strony; strona bez (prawie) zadnego tekstu - skan - idzie do OCR,
    gdy wolno. Zwraca (tekst, czy z OCR). Blad OCR zostawia strone bez tekstu."""
    text = str(page.get_text("text"))
    if not ocr_allowed or tessdata is None or len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
        return text, False
    try:
        return _ocr_text(page, tessdata), True
    except Exception as exc:
        sys.stderr.write(f"ocr failed on page: {exc}\n")
        return text, False


def _extract(
    path: str,
    max_pages: int,
    max_chars: int,
    budget_seconds: float,
    tessdata: str | None = None,
    max_ocr_pages: int = 0,
) -> dict[str, object]:
    import pymupdf

    try:
        document = pymupdf.open(path, filetype="pdf")
    except Exception:
        return {"ok": False, "error": "broken"}
    with document:
        if document.needs_pass:
            return {"ok": False, "error": "encrypted"}
        pages = document.page_count
        if pages <= 0:
            return {"ok": False, "error": "no_pages"}
        started = time.monotonic()
        readable = min(pages, max_pages)
        truncated = pages > max_pages
        parts: list[str] = []
        collected = 0
        ocr_pages = 0
        for index in range(readable):
            text, used_ocr = _page_text(document[index], ocr_pages < max_ocr_pages, tessdata)
            ocr_pages += used_ocr
            # strona tez z limitem - jedna strona moze miec ogromny tekst
            text = text[: max_chars + 1]
            parts.append(text)
            collected += len(text)
            if collected > max_chars:
                truncated = True
                break
            if index + 1 < readable and time.monotonic() - started >= budget_seconds:
                truncated = True
                break
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text, truncated = text[:max_chars], True
    return {"ok": True, "text": text, "pages": pages, "truncated": truncated, "ocr": ocr_pages > 0}


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def main(argv: list[str]) -> int:
    path, max_pages, max_chars, budget, memory_mb, *ocr_args = argv
    # OCR: katalog tessdata ("" = bez OCR) i limit stron OCR
    tessdata = ocr_args[0] if ocr_args and ocr_args[0] else None
    max_ocr_pages = int(ocr_args[1]) if len(ocr_args) > 1 else 0
    # wynik pojdzie na zachowany stdout; w trakcie pracy fd 1 i sys.stdout -> stderr
    sys.stdout.flush()
    result_fd = os.dup(STDOUT_FD)
    original_stdout = sys.stdout
    os.dup2(STDERR_FD, STDOUT_FD)
    sys.stdout = sys.stderr
    try:
        _limit_resources(int(memory_mb), float(budget))
        try:
            result = _extract(path, int(max_pages), int(max_chars), float(budget), tessdata, max_ocr_pages)
        except Exception:
            result = {"ok": False, "error": "broken"}
        sys.stderr.flush()
        _write_all(result_fd, json.dumps(result, ensure_ascii=False).encode("utf-8"))
    finally:
        os.dup2(result_fd, STDOUT_FD)
        os.close(result_fd)
        sys.stdout = original_stdout
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
