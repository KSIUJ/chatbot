"""Materialy studenckie z Mordoru (pipeline/scrapers/mordor): tekst i skany."""

from __future__ import annotations

import posixpath

from ...core.citations import Citation, text
from ...core.documents import Document
from ..base import RagSource
from . import loader


class MordorSource(RagSource):
    name = "mordor"

    def load_documents(self) -> list[Document]:
        return loader.load_documents()

    def label(self, hit: dict) -> str:
        return (hit.get("metadata") or {}).get("source_file", self.name)

    def cite(self, hit: dict) -> Citation | None:
        metadata = hit.get("metadata") or {}
        title = text(metadata.get("source_file")) or text(metadata.get("file_name"))
        if not title and hit.get("content_type") == "image":
            title = posixpath.basename(text(hit.get("value")).replace("\\", "/"))
        return {"kind": "mordor", "title": title, "url": None} if title else None
