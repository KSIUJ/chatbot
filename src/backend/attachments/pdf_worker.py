"""Wyciaganie tekstu z PDF w osobnym procesie (uruchamiane przez extract.py).

Samodzielny skrypt - importuje tylko biblioteke standardowa i pymupdf, bez
pakietu aplikacji. Zlosliwy PDF moze zawiesic albo zjesc pamiec parsera,
dlatego proces rodzica pilnuje twardego limitu czasu (kill), limitu bajtow
wyjscia i czystego srodowiska, a tu na Linuksie ustawiamy limit pamieci
(RLIMIT_AS) i czasu CPU. Tekst jest obcinany juz tutaj (MAX_ZNAKOW).

Podczas pracy stdout (takze deskryptor 1 - komunikaty bibliotek w C) idzie
na stderr; wynik trafia na zachowany oryginalny stdout, wiec nic nie zepsuje
JSON-a.

Uzycie: pdf_worker.py SCIEZKA MAX_STRON MAX_ZNAKOW BUDZET_S LIMIT_PAMIECI_MB
Wynik (stdout, jeden JSON w UTF-8):
  {"ok": true, "text": "...", "pages": N, "truncated": bool}
  {"ok": false, "error": "encrypted" | "broken" | "no_pages"}
"""

from __future__ import annotations

import json
import os
import sys
import time

MB = 1024 * 1024
# zapas czasu CPU ponad budzet (start interpretera, import pymupdf)
CPU_SECONDS_MARGIN = 10
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


def _extract(path: str, max_pages: int, max_chars: int, budget_seconds: float) -> dict[str, object]:
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
        for index in range(readable):
            # strona tez z limitem - jedna strona moze miec ogromny tekst
            text = document[index].get_text("text")[: max_chars + 1]
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
    return {"ok": True, "text": text, "pages": pages, "truncated": truncated}


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def main(argv: list[str]) -> int:
    path, max_pages, max_chars, budget, memory_mb = argv
    # wynik pojdzie na zachowany stdout; w trakcie pracy fd 1 i sys.stdout -> stderr
    sys.stdout.flush()
    result_fd = os.dup(STDOUT_FD)
    original_stdout = sys.stdout
    os.dup2(STDERR_FD, STDOUT_FD)
    sys.stdout = sys.stderr
    try:
        _limit_resources(int(memory_mb), float(budget))
        try:
            result = _extract(path, int(max_pages), int(max_chars), float(budget))
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
