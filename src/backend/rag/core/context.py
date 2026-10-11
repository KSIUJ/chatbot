"""
Publiczny interfejs RAG dla warstwy LLM: retrieve_context(query) -> tekst
kontekstu do promptu, sciezki plikow-obrazow i zrodla odpowiedzi. Wywoluje go
llm/generate.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from ..sources.base import RagSource
from .citations import Citation, collect_citations
from .index_store import LocationWatch
from .retrieval import Retriever, Section

_default_retriever: Retriever | None = None
_watch: LocationWatch | None = None
_index_name: str | None = None


def default_retriever() -> Retriever:
    """Wspolny retriever procesu (modele i indeksy laduja sie przy pierwszym uzyciu).

    Po przelaczeniu indeksu (python -m src.backend.rag.index build/sync)
    powstaje nowy retriever z tym samym encoderem - zrodla odbudowuja wtedy
    swoj stan, np. slownik nazwisk pracownikow."""
    global _default_retriever, _watch, _index_name
    if _watch is None:
        _watch = LocationWatch()
    name = _watch.current().name
    if _default_retriever is None:
        _default_retriever = Retriever()
    elif name != _index_name:
        _default_retriever = Retriever(encoder=_default_retriever.encoder)
    _index_name = name
    return _default_retriever


def loaded_retriever() -> Retriever | None:
    """Wspolny retriever, jesli juz powstal (diagnostyka nie laduje modeli)."""
    return _default_retriever


class RagContext(NamedTuple):
    prompt: str
    image_paths: list[str]
    # zrodla wszystkich trafien uzytych w kontekscie (tekst i obrazy)
    citations: list[Citation]


def _format_fragment(hit: dict, sources: Mapping[str, RagSource]) -> str:
    name = hit.get("source", "?")
    source = sources.get(name)
    label = source.label(hit) if source is not None else name
    return f"[{name}: {label}]\n{hit['value']}"


def _section(section: Section, sources: Mapping[str, RagSource]) -> str | None:
    fragments = [_format_fragment(h, sources) for h in section.hits if h.get("content_type") == "text"]
    if not fragments:
        return None
    return section.header + "\n\n" + "\n\n".join(fragments)


def render_sections(sections: list[Section], sources: Mapping[str, RagSource]) -> str:
    """Tekst kontekstu z sekcji: naglowek i fragmenty tekstowe; puste sekcje odpadaja."""
    return "\n\n".join(text for text in (_section(s, sources) for s in sections) if text)


def retrieve_context(query: str, retriever: Retriever | None = None) -> RagContext:
    """Kontekst dla zapytania: prompt, obrazy i zrodla.

    - prompt: fragmenty tekstowe oznaczone zrodlem, w sekcjach z
      Retriever.retrieve (dokladne wyszukiwania, potem pule z rejestru).
    - obrazy: wartosci trafien z content_type == "image" (skany, plany) -
      dolaczane do odpowiedzi jako pliki.
    - zrodla: strony, profile USOS i pliki z tych trafien, bez powtorzen.

    Brak trafien (np. pusty vectorstore) daje ("", [], []) zamiast wyjatku.
    """
    retriever = retriever or default_retriever()
    sections = retriever.retrieve(query)
    sources = retriever.sources

    prompt = render_sections(sections, sources)
    hits = [hit for section in sections for hit in section.hits]
    image_paths = [h["value"] for h in hits if h.get("content_type") == "image"]

    def cite(hit: dict) -> Citation | None:
        source = sources.get(hit.get("source", ""))
        return source.cite(hit) if source is not None else None

    return RagContext(prompt, image_paths, collect_citations(hits, cite))
