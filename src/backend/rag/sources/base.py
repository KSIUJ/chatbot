"""
Kontrakt zrodla RAG-a. Zrodlo (USOS, Mordor, strony UJ, KSI) jest jedynym
miejscem, ktore zna swoje dane: format zbioru w data/<zrodlo>/ (dataset.py,
DATASETS.md), zamiana rekordow na dokumenty indeksu, podpis trafienia
w kontekscie modelu i zrodlo odpowiedzi. Rdzen (rag/core/) operuje tylko na
tym kontrakcie i na Document.

Zrodlo moze tez miec dokladne wyszukiwanie (lookup) obok wyszukiwania
wektorowego i BM25 - np. pracownika po nazwisku. Jego trafienia trafiaja do
osobnej sekcji kontekstu (lookup_header) przed pulami (rag/registry.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.citations import Citation
    from ..core.datasets import Record
    from ..core.documents import Document
    from ..core.lexical import LexicalIndex
    from ..core.vectorstore import VectorStore


class RagSource(ABC):
    # klucz zrodla w indeksie (Document.source) i w zapisanych zrodlach odpowiedzi
    name: str
    # model rekordu zbioru data/<zrodlo>/ (dataset.py zrodla)
    record_model: type[Record]

    # dokladne wyszukiwanie: naglowek sekcji i ile trafien; None = brak
    lookup_header: str | None = None
    lookup_limit: int = 0

    def dataset_dir(self, data_dir: Path) -> Path:
        return data_dir / self.name

    @abstractmethod
    def load_documents(self, data_dir: Path) -> list[Document]:
        """Zbior zrodla z data_dir/<zrodlo>/ jako dokumenty (ingest). Brak
        zbioru = pusta lista; zbior niezgodny z formatem = DatasetError."""

    def convert_legacy(self, data_dir: Path) -> list[Record] | None:
        """Rekordy ze starego wyjscia scrapera (do czasu jego przebudowy);
        None = zrodlo nie ma starego formatu albo brak plikow."""
        return None

    @abstractmethod
    def label(self, hit: dict) -> str:
        """Podpis fragmentu w kontekscie modelu: [<zrodlo>: <podpis>]."""

    @abstractmethod
    def cite(self, hit: dict) -> Citation | None:
        """Zrodlo odpowiedzi dla trafienia; None, gdy nie ma czego pokazac."""

    def prepare_lookup(self, vectorstore: VectorStore, lexical: LexicalIndex) -> bool:
        """Przygotowanie dokladnego wyszukiwania z indeksow; False = jeszcze nie
        da sie (np. brak danych) - retriever sprobuje ponownie pozniej."""
        return False

    def lookup(self, query: str, limit: int) -> list[str]:
        """Id dokumentow znalezionych dokladnym wyszukiwaniem (pusto = nic)."""
        return []
