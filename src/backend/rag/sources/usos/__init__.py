"""Pracownicy wydzialu z USOS (pipeline/scrapers/usos): karta pracownika
i dokladne wyszukiwanie po imieniu i nazwisku (staff.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.citations import Citation, http_url, text
from ...core.documents import Document
from ..base import RagSource
from . import loader
from .staff import DEFAULT_LIMIT, StaffIndex

if TYPE_CHECKING:
    from ...core.lexical import LexicalIndex
    from ...core.vectorstore import VectorStore

# Nazwa sekcji PRACOWNIK wystepuje w prompcie systemowym (llm/generate.py).
STAFF_HEADER = "PRACOWNIK (dane z USOS - najbardziej wiarygodne):"


class UsosSource(RagSource):
    name = "usos"
    lookup_header = STAFF_HEADER
    lookup_limit = DEFAULT_LIMIT

    def __init__(self) -> None:
        self._staff: StaffIndex | None = None

    def load_documents(self) -> list[Document]:
        return loader.load_documents()

    def label(self, hit: dict) -> str:
        return (hit.get("metadata") or {}).get("employee_name", self.name)

    def cite(self, hit: dict) -> Citation | None:
        metadata = hit.get("metadata") or {}
        name = text(metadata.get("employee_name"))
        if not name:
            return None
        return {"kind": "usos", "title": name, "url": http_url(metadata.get("profile_url"))}

    def prepare_lookup(self, vectorstore: VectorStore, lexical: LexicalIndex) -> bool:
        if self._staff is None and lexical.count(self.name):
            self._staff = StaffIndex.from_collection(vectorstore.collection, lexical)
        return self._staff is not None

    def lookup(self, query: str, limit: int) -> list[str]:
        if self._staff is None or limit <= 0:
            return []
        return self._staff.lookup(query, limit=limit)
