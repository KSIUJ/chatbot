"""Rekordy materialow -> dokumenty indeksu: tekst w chunkach, skany i obrazy
jako pliki (wyszukiwane po sciezce, dolaczane do odpowiedzi).

Kazdy chunk zaczyna sie linia kontekstu: przedmiot, rodzaj materialu, rok
akademicki, nazwa pliku, strona i sekcja, np. "Analiza 1 › kolokwium ›
2023/24 › kol1.pdf › strona 2". Tekst z podzialem na strony (pages) jest
dzielony strona po stronie.
"""

from __future__ import annotations

import posixpath
from pathlib import Path

from ...core.chunking import CONTEXT_SEPARATOR, chunk_markdown, context_line, make_splitter, with_context
from ...core.documents import Document, make_id
from .dataset import MaterialRecord


def _material_context(record: MaterialRecord) -> list[str]:
    a = record.attributes
    return [a.course, a.material_kind, a.academic_year]


def _file_document(source: str, record: MaterialRecord, file_path: str) -> Document:
    # sciezka bez rozszerzenia, separatory jako spacje: "Analiza 1 2024 kolokwium"
    path_words = posixpath.splitext(record.attributes.path)[0].replace("/", " ").replace("_", " ").replace("-", " ")
    return Document(
        id=make_id(source, file_path),
        source=source,
        embed_text=with_context(context_line(*_material_context(record)), path_words),
        content_type="image",
        value=file_path,
        metadata={"file_name": posixpath.basename(record.attributes.path), "directory": posixpath.dirname(file_path)},
    )


def _text_parts(record: MaterialRecord) -> list[tuple[int, bool, str]]:
    """(numer strony albo 0, czy z OCR, tekst): strony, gdy sa, inaczej content."""
    pages = [(p.number, p.ocr, p.text) for p in record.attributes.pages if p.text.strip()]
    return pages or [(0, False, record.content)]


def material_documents(source: str, dataset_dir: Path, records: list[MaterialRecord]) -> list[Document]:
    splitter = make_splitter()
    documents: list[Document] = []
    for record in records:
        a = record.attributes
        file_path = (dataset_dir / a.path).as_posix()
        if record.kind != "text":
            documents.append(_file_document(source, record, file_path))
            continue
        file_name = posixpath.basename(a.path)
        index = 0
        for page, ocr, text in _text_parts(record):
            page_label = f"strona {page}" if page else ""
            for chunk in chunk_markdown(text, splitter):
                context = context_line(*_material_context(record), record.title or file_name, page_label, *chunk.section)
                chunk_text = with_context(context, chunk.text)
                documents.append(
                    Document(
                        id=make_id(source, file_path, str(index)),
                        source=source,
                        embed_text=chunk_text,
                        content_type="text",
                        value=chunk_text,
                        metadata={
                            "source_file": file_name,
                            "file_type": f".{a.file_type}",
                            "directory": posixpath.dirname(file_path),
                            "course": a.course,
                            "academic_year": a.academic_year,
                            "material_kind": a.material_kind,
                            "page": page,
                            "ocr": ocr,
                            "section": CONTEXT_SEPARATOR.join(chunk.section),
                            "chunk_index": index,
                        },
                    )
                )
                index += 1
    return documents
