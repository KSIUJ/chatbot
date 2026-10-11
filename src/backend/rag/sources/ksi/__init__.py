"""Informacje o KSI: strony KSI (data/ksi/, format jak uj_pages) i notatki
pisane recznie (knowledge/ksi/, notes.py)."""

from __future__ import annotations

from pathlib import Path

from ...core.chunking import CONTEXT_SEPARATOR, chunk_markdown, context_line, make_splitter, with_context
from ...core.citations import Citation, http_url, page_title, text
from ...core.datasets import read_dataset
from ...core.documents import Document, make_id
from ...core.lexical import tokenize
from ..base import RagSource
from ..uj_pages.dataset import PageRecord
from ..uj_pages.documents import page_documents
from .dataset import NoteRecord
from .notes import KNOWLEDGE_DIR, read_notes

KSI_LABEL = "KSI"


def _note_context(note: NoteRecord, section: tuple[str, ...]) -> str:
    """Linia kontekstu notatki: "KSI" (gdy tytul go nie zawiera), tytul, sekcja."""
    mentions_ksi = "ksi" in tokenize(note.title)
    return context_line("" if mentions_ksi else KSI_LABEL, note.title, *section)


def note_documents(source: str, notes: list[NoteRecord]) -> list[Document]:
    splitter = make_splitter()
    documents: list[Document] = []
    for note in notes:
        for index, chunk in enumerate(chunk_markdown(note.content, splitter)):
            text = with_context(_note_context(note, chunk.section), chunk.text)
            documents.append(
                Document(
                    id=make_id(source, "note", note.id, str(index)),
                    source=source,
                    embed_text=text,
                    content_type="text",
                    value=text,
                    metadata={
                        "note": note.id,
                        "title": note.title,
                        "url": note.url or "",
                        "always_include": note.attributes.always_include,
                        "section": CONTEXT_SEPARATOR.join(chunk.section),
                        "chunk_index": index,
                    },
                )
            )
    return documents


class KsiSource(RagSource):
    name = "ksi"
    record_model = PageRecord

    def __init__(self, notes_dir: Path = KNOWLEDGE_DIR) -> None:
        self.notes_dir = notes_dir

    def load_documents(self, data_dir: Path) -> list[Document]:
        dataset = read_dataset(self.dataset_dir(data_dir), self.name, PageRecord)
        pages = page_documents(self.name, dataset.records) if dataset else []
        return pages + note_documents(self.name, read_notes(self.notes_dir))

    def label(self, hit: dict) -> str:
        metadata = hit.get("metadata") or {}
        return text(metadata.get("title")) or text(metadata.get("url")) or self.name

    def cite(self, hit: dict) -> Citation | None:
        metadata = hit.get("metadata") or {}
        url = http_url(metadata.get("url"))
        title = text(metadata.get("title")) or (page_title(url) if url else "")
        return {"kind": "ksi", "title": title, "url": url} if title else None
