"""Strony wydzialu i uczelni (crawler pipeline/scrapers/strony)."""

from __future__ import annotations

from ...core.citations import Citation, http_url, page_title
from ...core.documents import Document
from ..base import RagSource
from . import loader


class StronySource(RagSource):
    name = "strony"

    def load_documents(self) -> list[Document]:
        return loader.load_documents()

    def label(self, hit: dict) -> str:
        return (hit.get("metadata") or {}).get("url", self.name)

    def cite(self, hit: dict) -> Citation | None:
        url = http_url((hit.get("metadata") or {}).get("url"))
        return {"kind": "strony", "title": page_title(url), "url": url} if url else None
