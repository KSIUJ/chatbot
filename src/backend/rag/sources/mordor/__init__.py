"""Materialy studenckie z Mordoru (data/mordor/): tekst, skany i obrazy."""

from __future__ import annotations

import posixpath
from pathlib import Path

from ...core.citations import Citation, text
from ...core.datasets import read_dataset
from ...core.documents import Document
from ..base import RagSource
from . import legacy
from .dataset import MaterialRecord
from .documents import material_documents


class MordorSource(RagSource):
    name = "mordor"
    record_model = MaterialRecord

    def load_documents(self, data_dir: Path) -> list[Document]:
        directory = self.dataset_dir(data_dir)
        dataset = read_dataset(directory, self.name, MaterialRecord)
        return material_documents(self.name, directory, dataset.records) if dataset else []

    def convert_legacy(self, data_dir: Path) -> list[MaterialRecord] | None:
        return legacy.convert(data_dir)

    def label(self, hit: dict) -> str:
        return (hit.get("metadata") or {}).get("source_file", self.name)

    def cite(self, hit: dict) -> Citation | None:
        metadata = hit.get("metadata") or {}
        title = text(metadata.get("source_file")) or text(metadata.get("file_name"))
        if not title and hit.get("content_type") == "image":
            title = posixpath.basename(text(hit.get("value")).replace("\\", "/"))
        return {"kind": "mordor", "title": title, "url": None} if title else None
