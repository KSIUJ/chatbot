"""Budowanie plikow testowych dla zalacznikow: PDF (PyMuPDF), DOCX (zip
z word/document.xml), obrazy (same naglowki wystarczaja do rozpoznania)."""

from __future__ import annotations

import io
import zipfile

import pymupdf

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64

_DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>{body}</w:body></w:document>"
)
_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
)


def pdf_bytes(*pages: str, user_password: str | None = None) -> bytes:
    """PDF z jedna strona na tekst; z haslem uzytkownika - zaszyfrowany."""
    doc = pymupdf.open()
    for text in pages or ("",):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    if user_password is None:
        return doc.tobytes()
    return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=user_password, owner_pw="owner")


def docx_bytes(*paragraphs: str, document_xml: str | None = None) -> bytes:
    """Minimalny DOCX: [Content_Types].xml i word/document.xml z akapitami."""
    if document_xml is None:
        body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
        document_xml = _DOCUMENT_XML.format(body=body)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def zip_bomb_docx(uncompressed_mb: int) -> bytes:
    """DOCX, ktorego document.xml po rozpakowaniu ma uncompressed_mb MB
    (same spacje - po kompresji kilkadziesiat KB)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("word/document.xml", " " * (uncompressed_mb * 1024 * 1024))
    return buffer.getvalue()


def zip_with_many_entries(count: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", _DOCUMENT_XML.format(body=""))
        for index in range(count):
            archive.writestr(f"word/media/{index}.txt", "x")
    return buffer.getvalue()


def plain_zip() -> bytes:
    """Zwykle archiwum zip bez word/document.xml - to nie DOCX."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")
    return buffer.getvalue()
