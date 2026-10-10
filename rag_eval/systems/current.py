"""Obecny RAG (src/backend/rag/) jako system pod testem.

Te same sekcje, ktore trafiaja do kontekstu modelu (Retriever.retrieve), ale
jako lista trafien, nie gotowy tekst. Zapytanie przechodzi przez
llm.rewrite.condense jak w produkcji (przy LLM_PROVIDER innym niz ollama bez
zmian).
"""

from __future__ import annotations

import os

from src.backend.llm.rewrite import condense
from src.backend.rag.core.context import render_sections
from src.backend.rag.core.retrieval import Retriever

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
        sections = self.retriever.retrieve(query)
        return Retrieval(
            hits=[hit_targets(h) for section in sections for h in section.hits],
            context_chars=len(render_sections(sections, self.retriever.sources)),
            query=query,
        )
