"""
OCR zeskanowanych PDF-ow w procesie pdf_worker.py: strony bez warstwy
tekstowej sa rozpoznawane Tesseractem (przez PyMuPDF), gdy sa dane jezykowe
(tessdata) dla pol i eng; limit stron OCR, dluzszy limit czasu, oznaczenie
tekstu OCR. Bez Tesseracta - jak dotad, bez tekstu.
"""

from __future__ import annotations

import json
import logging
import textwrap

import pytest

from src.backend.attachments import extract as extract_module
from src.backend.attachments import pdf_worker
from src.backend.attachments.extract import extract, find_tessdata
from tests.backend.attachments.attachment_files import pdf_bytes, scanned_pdf_bytes


@pytest.fixture
def fake_ocr(monkeypatch):
    calls: list[int] = []

    def ocr(page, tessdata):
        calls.append(page.number)
        return f"rozpoznany tekst strony {page.number + 1}"

    monkeypatch.setattr(pdf_worker, "_ocr_text", ocr)
    return calls


def _scanned(tmp_path, *pages: str):
    path = tmp_path / "skan.pdf"
    path.write_bytes(scanned_pdf_bytes(*pages))
    return str(path)


# --- worker ------------------------------------------------------------------------------

def test_scanned_pages_are_ocred_when_tessdata_is_available(tmp_path, fake_ocr):
    result = pdf_worker._extract(_scanned(tmp_path, "Regulamin"), 100, 60_000, 20.0, "/tessdata", 20)

    assert result["ok"] is True
    assert "rozpoznany tekst strony 1" in result["text"]
    assert result["ocr"] is True
    assert fake_ocr == [0]


def test_ocr_page_cap(tmp_path, fake_ocr):
    result = pdf_worker._extract(_scanned(tmp_path, "a", "b", "c"), 100, 60_000, 20.0, "/tessdata", 2)

    assert fake_ocr == [0, 1]
    assert "strony 2" in result["text"]
    assert "strony 3" not in result["text"]


def test_pages_with_text_layer_are_not_ocred(tmp_path, fake_ocr):
    path = tmp_path / "tekst.pdf"
    path.write_bytes(pdf_bytes("Ta strona ma zwykla warstwe tekstowa"))

    result = pdf_worker._extract(str(path), 100, 60_000, 20.0, "/tessdata", 20)

    assert fake_ocr == []
    assert result["ocr"] is False
    assert "warstwe tekstowa" in result["text"]


def test_no_ocr_without_tessdata(tmp_path, fake_ocr):
    result = pdf_worker._extract(_scanned(tmp_path, "Regulamin"), 100, 60_000, 20.0, None, 20)

    assert fake_ocr == []
    assert result["ocr"] is False
    assert result["text"].strip() == ""


def test_ocr_failure_keeps_the_page_without_text(tmp_path, monkeypatch):
    def broken(page, tessdata):
        raise RuntimeError("tesseract crashed")

    monkeypatch.setattr(pdf_worker, "_ocr_text", broken)

    result = pdf_worker._extract(_scanned(tmp_path, "x"), 100, 60_000, 20.0, "/tessdata", 20)

    assert result["ok"] is True
    assert result["ocr"] is False


# --- rodzic: wykrywanie tessdata, argumenty, limit czasu ------------------------------------

def _tessdata(tmp_path, *languages: str):
    root = tmp_path / "tessdata"
    root.mkdir()
    for language in languages:
        (root / f"{language}.traineddata").write_bytes(b"x")
    return root


def test_find_tessdata_from_env(tmp_path, monkeypatch):
    root = _tessdata(tmp_path, "pol", "eng")
    monkeypatch.setenv("TESSDATA_PREFIX", str(root))

    assert find_tessdata() == root


def test_find_tessdata_requires_both_languages(tmp_path, monkeypatch):
    monkeypatch.setenv("TESSDATA_PREFIX", str(_tessdata(tmp_path, "eng")))
    monkeypatch.setattr(extract_module, "TESSDATA_CANDIDATES", ())

    assert find_tessdata() is None


def test_find_tessdata_from_standard_locations(tmp_path, monkeypatch):
    root = _tessdata(tmp_path, "pol", "eng")
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    monkeypatch.setattr(extract_module, "TESSDATA_CANDIDATES", (str(tmp_path / "missing"), str(root)))

    assert find_tessdata() == root


def test_worker_gets_tessdata_ocr_limits_and_longer_timeout(tmp_path, monkeypatch):
    root = _tessdata(tmp_path, "pol", "eng")
    monkeypatch.setattr(extract_module, "find_tessdata", lambda: root)
    script = tmp_path / "echo_worker.py"
    script.write_text(textwrap.dedent("""
        import json, os, sys
        seen = {"argv": sys.argv[1:], "tessdata_env": os.environ.get("TESSDATA_PREFIX")}
        sys.stdout.write(json.dumps({"ok": True, "text": json.dumps(seen), "pages": 1, "truncated": False, "ocr": True}))
    """), encoding="utf-8")
    monkeypatch.setattr(extract_module, "PDF_WORKER_SCRIPT", script)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(pdf_bytes("x"))

    result = extract(pdf, "pdf")

    seen = json.loads(result.text)
    assert seen["argv"][5:] == [str(root), str(extract_module.MAX_OCR_PAGES)]
    assert seen["tessdata_env"] == str(root)
    # budzet czytania (argument 4) dla sciezki OCR jest dluzszy
    assert float(seen["argv"][3]) == extract_module.PDF_OCR_TIME_BUDGET_SECONDS
    assert result.ocr is True


def test_ocr_path_gets_a_longer_hard_timeout(tmp_path):
    assert extract_module._worker_timeout(None) == extract_module.PDF_HARD_TIMEOUT_SECONDS
    assert extract_module._worker_timeout(tmp_path) == extract_module.PDF_OCR_HARD_TIMEOUT_SECONDS
    assert extract_module.PDF_OCR_HARD_TIMEOUT_SECONDS > extract_module.PDF_HARD_TIMEOUT_SECONDS


def test_missing_ocr_is_logged_once(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(extract_module, "find_tessdata", lambda: None)
    monkeypatch.setattr(extract_module, "_ocr_unavailable_logged", False)
    pdf = tmp_path / "skan.pdf"
    pdf.write_bytes(scanned_pdf_bytes("Regulamin"))

    with caplog.at_level(logging.WARNING, logger="src.backend.attachments"):
        first = extract(pdf, "pdf")
        extract(pdf, "pdf")

    assert first.text == ""
    assert first.ocr is False
    assert caplog.text.count("OCR unavailable") == 1


# --- prawdziwy Tesseract (obraz Dockera; lokalnie zwykle pominiete) -----------------------------

@pytest.mark.skipif(find_tessdata() is None, reason="brak danych Tesseracta (pol, eng)")
def test_real_ocr_recognises_polish_scan(tmp_path):
    pdf = tmp_path / "skan.pdf"
    pdf.write_bytes(scanned_pdf_bytes("Regulamin studiów na Wydziale Matematyki i Informatyki"))

    result = extract(pdf, "pdf")

    assert result.ocr is True
    assert "Regulamin" in result.text
    assert "Informatyki" in result.text
