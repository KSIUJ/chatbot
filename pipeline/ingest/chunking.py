"""Wspolny podzial tekstu na chunki dla zrodel mordor i strony."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

# Zmiana parametrow zmienia chunki (i ich id) - wymaga ponownego ingestu z --purge.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def make_splitter() -> RecursiveCharacterTextSplitter:
    """Splitter o parametrach CHUNK_SIZE/CHUNK_OVERLAP."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
