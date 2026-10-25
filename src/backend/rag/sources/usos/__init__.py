"""USOS (data/usos/): pracownicy wydzialu z karta i dokladnym wyszukiwaniem po
imieniu i nazwisku (staff.py) oraz aktualnosci, strony informacyjne USOSweb,
jednostki, przedmioty z planem zajec, studia, kalendarz akademicki,
rejestracje, budynki i akademiki (dataset.py)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ...core.citations import Citation, http_url, text
from ...core.datasets import read_dataset
from ...core.documents import Document
from ..base import RagSource
from .dataset import USOS_RECORD, StaffRecord
from .documents import STAFF_KIND, entry_documents, staff_document
from .staff import DEFAULT_LIMIT, StaffIndex

if TYPE_CHECKING:
    from ...core.lexical import LexicalIndex
    from ...core.vectorstore import VectorStore

# Nazwa sekcji PRACOWNIK wystepuje w prompcie systemowym (llm/generate.py).
STAFF_HEADER = "PRACOWNIK (dane z USOS - najbardziej wiarygodne):"


def _is_staff(metadata: dict) -> bool:
    # indeksy sprzed rekordow innych rodzajow nie maja "kind" - byly tam sami pracownicy
    return metadata.get("kind", STAFF_KIND) == STAFF_KIND


class UsosSource(RagSource):
    name = "usos"
    record_model = USOS_RECORD
    lookup_header = STAFF_HEADER
    lookup_limit = DEFAULT_LIMIT

    def __init__(self) -> None:
        self._staff: StaffIndex | None = None

    def load_documents(self, data_dir: Path) -> list[Document]:
        dataset = read_dataset(self.dataset_dir(data_dir), self.name, USOS_RECORD)
        if dataset is None:
            return []
        staff = [record for record in dataset.records if isinstance(record, StaffRecord)]
        others = [record for record in dataset.records if not isinstance(record, StaffRecord)]
        return [staff_document(self.name, record) for record in staff] + entry_documents(self.name, others)

    def label(self, hit: dict) -> str:
        metadata = hit.get("metadata") or {}
        if _is_staff(metadata):
            return metadata.get("employee_name", self.name)
        return text(metadata.get("title")) or self.name

    def cite(self, hit: dict) -> Citation | None:
        metadata = hit.get("metadata") or {}
        if _is_staff(metadata):
            name = text(metadata.get("employee_name"))
            if not name:
                return None
            return {"kind": "usos", "title": name, "url": http_url(metadata.get("profile_url"))}
        title = text(metadata.get("title"))
        url = http_url(metadata.get("url"))
        if not title and url is None:
            return None
        return {"kind": "usos", "title": title or url or "", "url": url}

    def prepare_lookup(self, vectorstore: VectorStore, lexical: LexicalIndex) -> bool:
        if self._staff is None and lexical.count(self.name):
            self._staff = StaffIndex.from_collection(vectorstore.collection, lexical)
        return self._staff is not None

    def lookup(self, query: str, limit: int) -> list[str]:
        if self._staff is None or limit <= 0:
            return []
        return self._staff.lookup(query, limit=limit)
