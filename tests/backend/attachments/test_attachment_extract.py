"""
Wyciaganie tekstu z zalacznikow przy wysylaniu pliku: PDF (PyMuPDF, limit
stron, zaszyfrowane i uszkodzone pliki), DOCX (wlasny odczyt
word/document.xml z oslona przed zip bombami), TXT; obrazy bez tekstu.
"""

import pytest

from src.backend.attachments import extract as extract_module
from src.backend.attachments.extract import (
    MAX_EXTRACTED_CHARS,
    TRUNCATION_NOTE,
    UnreadableFile,
    extract,
)
from tests.backend.attachments.attachment_files import (
    PNG_BYTES,
    docx_bytes,
    pdf_bytes,
    zip_bomb_docx,
    zip_with_many_entries,
)


def _file(tmp_path, data: bytes):
    path = tmp_path / "upload.bin"
    path.write_bytes(data)
    return path


# --- PDF -----------------------------------------------------------------------

def test_pdf_text_and_page_count(tmp_path):
    result = extract(_file(tmp_path, pdf_bytes("Strona pierwsza", "Strona druga")), "pdf")

    assert result.pages == 2
    assert "Strona pierwsza" in result.text
    assert "Strona druga" in result.text
    assert result.text.index("pierwsza") < result.text.index("druga")


def test_pdf_page_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_module, "MAX_PDF_PAGES", 2)

    result = extract(_file(tmp_path, pdf_bytes("jeden", "dwa", "trzy")), "pdf")

    assert result.pages == 3
    assert "dwa" in result.text
    assert "trzy" not in result.text
    assert TRUNCATION_NOTE in result.text


def test_encrypted_pdf_is_unreadable(tmp_path):
    with pytest.raises(UnreadableFile):
        extract(_file(tmp_path, pdf_bytes("tajne", user_password="haslo")), "pdf")


@pytest.mark.parametrize("data", [b"%PDF-1.7\nto nie jest pdf", pdf_bytes("ucieta")[:200]])
def test_broken_pdf_is_unreadable(tmp_path, data):
    with pytest.raises(UnreadableFile):
        extract(_file(tmp_path, data), "pdf")


def test_pdf_time_budget_stops_extraction(tmp_path, monkeypatch):
    # budzet czasu wyczerpany od razu - zostaje tylko pierwsza strona
    # (sciezka bez OCR - z Tesseractem obowiazuje PDF_OCR_TIME_BUDGET_SECONDS)
    monkeypatch.setattr(extract_module, "find_tessdata", lambda: None)
    monkeypatch.setattr(extract_module, "PDF_TIME_BUDGET_SECONDS", 0.0)

    result = extract(_file(tmp_path, pdf_bytes("jeden", "dwa")), "pdf")

    assert "jeden" in result.text
    assert "dwa" not in result.text
    assert TRUNCATION_NOTE in result.text


# --- DOCX ----------------------------------------------------------------------

def test_docx_paragraphs(tmp_path):
    result = extract(_file(tmp_path, docx_bytes("Pierwszy akapit", "Drugi &amp; ostatni")), "docx")

    assert result.text.splitlines() == ["Pierwszy akapit", "Drugi & ostatni"]
    assert result.pages is None


def test_docx_ignores_markup_and_entities_from_dtd(tmp_path):
    xml = (
        '<?xml version="1.0"?><!DOCTYPE w [<!ENTITY a "AAAAAAAAAA">]>'
        '<w:document xmlns:w="x"><w:body><w:p><w:r><w:t xml:space="preserve">Tekst &a;</w:t></w:r>'
        "<w:r><w:tab/><w:t>po tabie</w:t></w:r></w:p></w:body></w:document>"
    )

    result = extract(_file(tmp_path, docx_bytes(document_xml=xml)), "docx")

    # encje z DTD nie sa rozwijane (brak parsera XML = brak "billion laughs")
    assert result.text == "Tekst &a;\tpo tabie"


def test_docx_zip_bomb_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_module, "MAX_DOCX_XML_BYTES", 1024 * 1024)

    with pytest.raises(UnreadableFile):
        extract(_file(tmp_path, zip_bomb_docx(3)), "docx")


def test_docx_with_too_many_entries_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_module, "MAX_DOCX_ENTRIES", 10)

    with pytest.raises(UnreadableFile):
        extract(_file(tmp_path, zip_with_many_entries(20)), "docx")


def test_broken_zip_is_unreadable(tmp_path):
    with pytest.raises(UnreadableFile):
        extract(_file(tmp_path, docx_bytes("x")[:60]), "docx")


# --- TXT i obrazy ----------------------------------------------------------------

def test_txt_is_decoded_without_bom(tmp_path):
    result = extract(_file(tmp_path, "﻿Zażółć\r\nlinia".encode()), "txt")

    assert result.text == "Zażółć\nlinia"


def test_long_text_is_capped_with_note(tmp_path):
    result = extract(_file(tmp_path, b"a" * (MAX_EXTRACTED_CHARS + 500)), "txt")

    assert result.text.endswith(TRUNCATION_NOTE)
    assert len(result.text) <= MAX_EXTRACTED_CHARS + len(TRUNCATION_NOTE) + 2


@pytest.mark.parametrize("kind", ["png", "jpeg", "webp"])
def test_images_have_no_text(tmp_path, kind):
    result = extract(_file(tmp_path, PNG_BYTES), kind)

    assert result.text is None
    assert result.pages is None
