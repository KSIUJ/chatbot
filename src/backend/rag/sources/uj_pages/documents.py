"""Rekordy stron -> dokumenty indeksu (wspolne dla uj_pages i stron KSI).

Kazdy chunk zaczyna sie linia kontekstu: okruszki menu, tytul strony (albo
pliku) i sekcja, np. "O nas › Biblioteka › Godziny otwarcia" - ta sama linia
jest w tekscie do wyszukiwania i w tekscie dla modelu.
"""

from __future__ import annotations

from ...core.chunking import CONTEXT_SEPARATOR, chunk_markdown, context_line, make_splitter, with_context
from ...core.documents import Document, make_id
from .dataset import PageRecord


def page_documents(source: str, records: list[PageRecord]) -> list[Document]:
    """Kazda strona dzielona na chunki wedlug naglowkow (chunking.py); tylko
    tekst, bez obrazow."""
    splitter = make_splitter()
    documents: list[Document] = []
    for record in records:
        for index, chunk in enumerate(chunk_markdown(record.content, splitter)):
            context = context_line(*record.attributes.breadcrumbs, record.title, *chunk.section)
            text = with_context(context, chunk.text)
            documents.append(
                Document(
                    id=make_id(source, record.url, str(index)),
                    source=source,
                    embed_text=text,
                    content_type="text",
                    value=text,
                    metadata={
                        "url": record.url,
                        "domain": record.attributes.site,
                        "category": record.attributes.category,
                        "title": record.title,
                        "section": CONTEXT_SEPARATOR.join(chunk.section),
                        "chunk_index": index,
                    },
                )
            )
    return documents
