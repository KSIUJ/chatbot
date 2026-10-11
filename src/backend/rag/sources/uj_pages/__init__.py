"""Strony UJ: wydzial, USOSownia, kola naukowe, Wikipedia (data/uj_pages/)."""

from __future__ import annotations

from pathlib import Path

from ...core.citations import Citation, http_url, page_title
from ...core.datasets import read_dataset
from ...core.documents import Document
from ..base import RagSource
from . import legacy
from .dataset import PageRecord
from .documents import page_documents


class UjPagesSource(RagSource):
    name = "uj_pages"
    record_model = PageRecord

    def load_documents(self, data_dir: Path) -> list[Document]:
        dataset = read_dataset(self.dataset_dir(data_dir), self.name, PageRecord)
        return page_documents(self.name, dataset.records) if dataset else []

    def convert_legacy(self, data_dir: Path) -> list[PageRecord] | None:
        return legacy.convert(data_dir)

    def label(self, hit: dict) -> str:
        return (hit.get("metadata") or {}).get("url", self.name)

    def cite(self, hit: dict) -> Citation | None:
        url = http_url((hit.get("metadata") or {}).get("url"))
        return {"kind": self.name, "title": page_title(url), "url": url} if url else None
