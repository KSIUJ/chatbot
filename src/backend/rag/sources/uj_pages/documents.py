"""Rekordy stron -> dokumenty indeksu (wspolne dla uj_pages i stron KSI)."""

from __future__ import annotations

from ...core.chunking import make_splitter
from ...core.documents import Document, make_id
from .dataset import PageRecord


def page_documents(source: str, records: list[PageRecord]) -> list[Document]:
    """Kazda strona dzielona na chunki (chunking.py); tylko tekst, bez obrazow."""
    splitter = make_splitter()
    documents: list[Document] = []
    for record in records:
        for index, chunk in enumerate(splitter.split_text(record.content)):
            documents.append(
                Document(
                    id=make_id(source, record.url, str(index)),
                    source=source,
                    embed_text=chunk,
                    content_type="text",
                    value=chunk,
                    metadata={
                        "url": record.url,
                        "domain": record.attributes.site,
                        "category": record.attributes.category,
                        "title": record.title,
                        "chunk_index": index,
                    },
                )
            )
    return documents
