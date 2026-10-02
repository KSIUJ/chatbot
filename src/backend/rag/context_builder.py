"""
Publiczny interfejs RAG dla warstwy LLM: retrieve_context(query) -> tekst
kontekstu do promptu, sciezki plikow-obrazow i zrodla odpowiedzi. Wywoluje go
llm/generate.py; build_context zwraca same (tekst, obrazy).
"""

from typing import NamedTuple

from .retriever import Retriever
from .sources import Source, collect_sources
from .staff import DEFAULT_LIMIT as DEFAULT_STAFF_LIMIT

DEFAULT_K_MORDOR = 5
DEFAULT_K_OTHER = 5

STAFF_HEADER = "PRACOWNIK (dane z USOS - najbardziej wiarygodne):"
OFFICIAL_HEADER = "ZRODLA OFICJALNE (strony wydzialu, USOS - wiarygodne):"
# Naglowki sekcji wewnatrz bloku KONTEKST - nazwy PRACOWNIK, zrodla oficjalne
# i materialy studenckie z Mordoru wystepuja w prompcie systemowym (llm/generate.py).
MORDOR_HEADER = "MATERIALY STUDENCKIE (Mordor - notatki i skany, moga zawierac bledy lub byc nieaktualne):"

_default_retriever: Retriever | None = None


def _get_default_retriever() -> Retriever:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = Retriever()
    return _default_retriever


def _format_fragment(hit: dict) -> str:
    source = hit.get("source", "?")
    metadata = hit.get("metadata", {})

    if source == "mordor":
        label = metadata.get("source_file", "mordor")
    elif source == "strony":
        label = metadata.get("url", "strony")
    elif source == "usos":
        label = metadata.get("employee_name", "usos")
    else:
        label = source

    return f"[{source}: {label}]\n{hit['value']}"


def _section(header: str, hits: list[dict]) -> str | None:
    fragments = [_format_fragment(h) for h in hits if h.get("content_type") == "text"]
    if not fragments:
        return None
    return header + "\n\n" + "\n\n".join(fragments)


class RagContext(NamedTuple):
    prompt: str
    image_paths: list[str]
    # zrodla wszystkich trafien uzytych w kontekscie (tekst i obrazy)
    sources: list[Source]


def build_context(
    query: str,
    k_mordor: int = DEFAULT_K_MORDOR,
    k_other: int = DEFAULT_K_OTHER,
    staff_limit: int = DEFAULT_STAFF_LIMIT,
    retriever: Retriever | None = None,
) -> tuple[str, list[str]]:
    """(prompt_z_kontekstem, lista_sciezek_do_obrazow) - patrz retrieve_context."""
    result = retrieve_context(
        query, k_mordor=k_mordor, k_other=k_other, staff_limit=staff_limit, retriever=retriever
    )
    return result.prompt, result.image_paths


def retrieve_context(
    query: str,
    k_mordor: int = DEFAULT_K_MORDOR,
    k_other: int = DEFAULT_K_OTHER,
    staff_limit: int = DEFAULT_STAFF_LIMIT,
    retriever: Retriever | None = None,
) -> RagContext:
    """Kontekst dla zapytania: prompt, obrazy i zrodla.

    - prompt_z_kontekstem: fragmenty tekstowe oznaczone zrodlem, w trzech
      sekcjach: pracownik (gdy zapytanie zawiera nazwisko z USOS), zrodla
      oficjalne, mordor. Mordor i zrodla oficjalne maja osobne pule miejsc
      (k_mordor / k_other), zeby duzo wiekszy mordor ich nie zagluszal.
    - lista_sciezek_do_obrazow: wartosci trafien z content_type == "image"
      (skany, plany) - dolaczane do odpowiedzi jako pliki.
    - zrodla: strony, profile USOS i pliki z tych trafien, bez powtorzen.

    Brak trafien (np. pusty vectorstore) daje ("", [], []) zamiast wyjatku.
    """
    retriever = retriever or _get_default_retriever()
    staff = retriever.retrieve_staff(query, limit=staff_limit)
    groups = retriever.retrieve_split(query, k_mordor=k_mordor, k_other=k_other)

    staff_ids = {h["id"] for h in staff}
    other = [h for h in groups["other"] if h["id"] not in staff_ids]

    sections = [
        section
        for section in (
            _section(STAFF_HEADER, staff),
            _section(OFFICIAL_HEADER, other),
            _section(MORDOR_HEADER, groups["mordor"]),
        )
        if section
    ]

    hits = staff + other + groups["mordor"]
    image_paths = [h["value"] for h in hits if h.get("content_type") == "image"]

    return RagContext("\n\n".join(sections), image_paths, collect_sources(hits))
