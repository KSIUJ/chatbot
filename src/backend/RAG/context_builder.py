"""
Publiczny interfejs modulu RAG dla src/backend/llm/.

Jedyna funkcja, jakiej potrzebuje warstwa LLM: build_context(query, k_mordor,
k_other) -> (prompt_z_kontekstem, lista_sciezek_do_obrazow). Reszta modulu RAG
(encoder/vectorstore/retriever/ingest) jest szczegolem implementacyjnym.

POZA ZAKRESEM tego zadania: faktyczne spiecie z src/backend/main.py (FastAPI)
- main.py jest na razie tylko placeholderem (# TODO fastapi), a
  src/backend/llm/ jest rownolegle rozwijane przez Mikolaja. To on decyduje,
  jak i kiedy wywolac build_context() w docelowym flow zapytanie -> odpowiedz.
"""

from .retriever import Retriever

DEFAULT_K_MORDOR = 5
DEFAULT_K_OTHER = 5
DEFAULT_STAFF_LIMIT = 2

STAFF_HEADER = "PRACOWNIK (dane z USOS - najbardziej wiarygodne):"
OFFICIAL_HEADER = "ZRODLA OFICJALNE (strony wydzialu, USOS - wiarygodne):"
MORDOR_HEADER = "MATERIALY STUDENCKIE (mordor - notatki i skany, moga byc nieaktualne):"

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


def build_context(
    query: str,
    k_mordor: int = DEFAULT_K_MORDOR,
    k_other: int = DEFAULT_K_OTHER,
    staff_limit: int = DEFAULT_STAFF_LIMIT,
    retriever: Retriever | None = None,
) -> tuple[str, list[str]]:
    """Zwraca (prompt_z_kontekstem, lista_sciezek_do_obrazow) dla danego
    zapytania uzytkownika.

    - prompt_z_kontekstem: tekstowe fragmenty (content_type == "text") ze
      zrodel wpisanych w prompt, oznaczone zrodlem/etykieta dla identyfikacji,
      w trzech osobnych sekcjach: trafienia z wyszukiwarki pracownikow (o ile
      zapytanie zawiera nazwisko z USOS), potem zrodla oficjalne, potem mordor. Kazda grupa ma wlasna pule miejsc (k_other / k_mordor),
      zeby 118k chunkow mordoru nie zagluszalo 1.4k wpisow oficjalnych.
    - lista_sciezek_do_obrazow: sciezki plikow dla trafien z
      content_type == "image" (np. plany budynkow, skany z mordoru) - warstwa
      LLM/frontend decyduje, jak je dolaczyc do odpowiedzi.

    Jesli nie znaleziono zadnych trafien (np. pusty vectorstore), zwraca
    pusty prompt i pusta liste obrazow - nie rzuca wyjatku, zeby brak danych
    zrodlowych nie wywalal calego flow zapytanie -> odpowiedz.
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

    return "\n\n".join(sections), image_paths
