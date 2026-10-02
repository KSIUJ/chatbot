"""
Rozpoznawanie rodzaju pliku po zawartosci (magic bytes), nie po nazwie ani
Content-Type, oraz bezpieczna nazwa pliku do wyswietlenia.
"""

import pytest

from src.backend.attachments.sniff import MAX_NAME_LENGTH, detect_kind, display_name
from tests.backend.attachments.attachment_files import (
    JPEG_BYTES,
    PNG_BYTES,
    WEBP_BYTES,
    docx_bytes,
    pdf_bytes,
    plain_zip,
)


def _file(tmp_path, data: bytes, name: str = "upload.bin"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (pdf_bytes("hello"), "pdf"),
        (PNG_BYTES, "png"),
        (JPEG_BYTES, "jpeg"),
        (WEBP_BYTES, "webp"),
        (docx_bytes("akapit"), "docx"),
        ("Zażółć gęślą jaźń\nlinia 2".encode(), "txt"),
        (b"\xef\xbb\xbfz BOM-em", "txt"),
    ],
)
def test_detects_kind_by_content(tmp_path, data, expected):
    assert detect_kind(_file(tmp_path, data)) == expected


@pytest.mark.parametrize("name", ["plan.png", "notatki.txt", "obraz.jpg", "dokument.docx"])
def test_spoofed_extension_does_not_matter(tmp_path, name):
    # PDF udajacy inny plik nadal jest PDF-em
    assert detect_kind(_file(tmp_path, pdf_bytes("x"), name)) == "pdf"


@pytest.mark.parametrize(
    "data",
    [
        b"MZ\x90\x00\x03\x00\x00\x00",  # plik wykonywalny Windows
        b"GIF89a\x01\x00\x01\x00",  # GIF - nieobslugiwany
        b"tekst z bajtem NUL\x00 w srodku",
        b"\xff\xfe\x00\x00 to nie UTF-8 \xc3\x28",
        b"RIFF\x24\x00\x00\x00WAVEfmt ",  # RIFF, ale nie WEBP
        b"",
    ],
)
def test_rejects_unknown_or_binary_content(tmp_path, data):
    assert detect_kind(_file(tmp_path, data)) is None


def test_plain_zip_is_not_docx(tmp_path):
    assert detect_kind(_file(tmp_path, plain_zip(), "raport.docx")) is None


def test_pdf_magic_must_be_at_the_start(tmp_path):
    # tekst wspominajacy %PDF- to nadal tekst, a nie PDF
    assert detect_kind(_file(tmp_path, b"Naglowek pliku PDF to %PDF-1.7")) == "txt"


def test_html_disguised_as_text_is_text_not_html(tmp_path):
    # tresc HTML jest poprawnym UTF-8 - przyjmujemy ja jako zwykly tekst
    assert detect_kind(_file(tmp_path, b"<html><script>alert(1)</script></html>", "x.html")) == "txt"


# --- nazwa do wyswietlenia ---------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "kind", "expected"),
    [
        ("Plan zajęć.pdf", "pdf", "Plan zajęć.pdf"),
        ("../../etc/passwd.txt", "txt", "passwd.txt"),
        ("C:\\Users\\jan\\notatki.txt", "txt", "notatki.txt"),
        ("zly\x00plik\x1b[31m.txt", "txt", "zlyplik[31m.txt"),
        ("zdjecie.JPG", "jpeg", "zdjecie.JPG"),
        ("zdjecie.jpeg", "jpeg", "zdjecie.jpeg"),
        # rozszerzenie niezgodne z trescia - dopisujemy wlasciwe
        ("strona.html", "txt", "strona.html.txt"),
        ("raport.png", "pdf", "raport.png.pdf"),
        ("bez_rozszerzenia", "docx", "bez_rozszerzenia.docx"),
        (None, "png", "plik.png"),
        ("   ", "pdf", "plik.pdf"),
        ("..", "txt", "plik.txt"),
        ("  .ukryty.txt  ", "txt", "ukryty.txt"),
    ],
)
def test_display_name_is_safe(raw, kind, expected):
    assert display_name(raw, kind) == expected


def test_display_name_is_capped_and_keeps_extension():
    name = display_name("a" * 500 + ".pdf", "pdf")

    assert len(name) <= MAX_NAME_LENGTH
    assert name.endswith(".pdf")
