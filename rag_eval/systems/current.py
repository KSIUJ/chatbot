"""Obecny RAG (src/backend/rag/) jako system pod testem.

Sklada kontekst tak jak context_builder.retrieve_context - pracownik, zrodla
oficjalne, Mordor - ale zwraca trafienia, nie gotowy tekst. Zapytanie
przechodzi przez llm.rewrite.condense jak w produkcji (przy LLM_PROVIDER
innym niz ollama bez zmian).
"""

from __future__ import annotations

import os

from src.backend.llm.rewrite import condense
from src.backend.rag import context_builder
from src.backend.rag.retriever import Retriever

from .. import targets
from ..questions import Question
from . import Retrieval


def hit_targets(hit: dict) -> frozenset[str]:
    metadata = hit.get("metadata") or {}
    source = hit.get("source")
    if source == "strony" and metadata.get("url"):
        return frozenset({targets.page(metadata["url"])})
    if source == "usos" and metadata.get("employee_name"):
        return frozenset({targets.staff(metadata["employee_name"])})
    if source == "mordor":
        name = metadata.get("source_file") or metadata.get("file_name") or ""
        path = os.path.join(metadata.get("directory") or "", name) if name else hit.get("value") or ""
        return frozenset({targets.mordor(path)})
    return frozenset()


class CurrentRag:
    name = "current"

    def __init__(self) -> None:
        self.retriever = Retriever()

    def retrieve(self, question: Question) -> Retrieval:
        history = [{"role": "user", "content": q} for q in question.history]
        query = condense(question.question, history)

        staff = self.retriever.retrieve_staff(query, limit=context_builder.DEFAULT_STAFF_LIMIT)
        groups = self.retriever.retrieve_split(
            query, k_mordor=context_builder.DEFAULT_K_MORDOR, k_other=context_builder.DEFAULT_K_OTHER
        )
        staff_ids = {h["id"] for h in staff}
        other = [h for h in groups["other"] if h["id"] not in staff_ids]
        hits = staff + other + groups["mordor"]

        sections = [
            section
            for section in (
                context_builder._section(context_builder.STAFF_HEADER, staff),
                context_builder._section(context_builder.OFFICIAL_HEADER, other),
                context_builder._section(context_builder.MORDOR_HEADER, groups["mordor"]),
            )
            if section
        ]
        return Retrieval(
            hits=[hit_targets(h) for h in hits],
            context_chars=len("\n\n".join(sections)),
            query=query,
        )
