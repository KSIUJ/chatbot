"""Pracownicy wydzialu z USOS (data/usos/): karta pracownika i dokladne
wyszukiwanie po imieniu i nazwisku (staff.py)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ...core.citations import Citation, http_url, text
from ...core.datasets import read_dataset
from ...core.documents import Document
from ..base import RagSource
from . import legacy
from .dataset import StaffRecord
from .documents import staff_document
from .staff import DEFAULT_LIMIT, StaffIndex

if TYPE_CHECKING:
    from ...core.lexical import LexicalIndex
    from ...core.vectorstore import VectorStore

# Nazwa sekcji PRACOWNIK wystepuje w prompcie systemowym (llm/generate.py).
STAFF_HEADER = "PRACOWNIK (dane z USOS - najbardziej wiarygodne):"


class UsosSource(RagSource):
    name = "usos"
    record_model = StaffRecord
    lookup_header = STAFF_HEADER
    lookup_limit = DEFAULT_LIMIT

    def __init__(self) -> None:
        self._staff: StaffIndex | None = None

    def load_documents(self, data_dir: Path) -> list[Document]:
        dataset = read_dataset(self.dataset_dir(data_dir), self.name, StaffRecord)
        return [staff_document(self.name, record) for record in dataset.records] if dataset else []

    def convert_legacy(self, data_dir: Path) -> list[StaffRecord] | None:
        return legacy.convert(data_dir)

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
