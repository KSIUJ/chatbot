"""
Publiczny interfejs modulu RAG dla src/backend/llm/.

Jedyna funkcja, jakiej potrzebuje warstwa LLM: build_context(query, top_k) ->
(prompt_z_kontekstem, lista_sciezek_do_obrazow). Reszta modulu RAG
(encoder/vectorstore/retriever/ingest) jest szczegolem implementacyjnym.

POZA ZAKRESEM tego zadania: faktyczne spiecie z src/backend/main.py (FastAPI)
- main.py jest na razie tylko placeholderem (# TODO fastapi), a
  src/backend/llm/ jest rownolegle rozwijane przez Mikolaja. To on decyduje,
  jak i kiedy wywolac build_context() w docelowym flow zapytanie -> odpowiedz.
"""

from .retriever import Retriever

DEFAULT_TOP_K = 5

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


def build_context(
    query: str, top_k: int = DEFAULT_TOP_K, retriever: Retriever | None = None
) -> tuple[str, list[str]]:
    """Zwraca (prompt_z_kontekstem, lista_sciezek_do_obrazow) dla danego
    zapytania uzytkownika.

    - prompt_z_kontekstem: tekstowe fragmenty (content_type == "text") ze
      zrodel wpisanych w promptt, oznaczone zrodlem/etykieta dla identyfikacji.
    - lista_sciezek_do_obrazow: sciezki plikow dla trafien z
      content_type == "image" (np. plany budynkow, skany z mordoru) - warstwa
      LLM/frontend decyduje, jak je dolaczyc do odpowiedzi.

    Jesli nie znaleziono zadnych trafien (np. pusty vectorstore), zwraca
    pusty prompt i pusta liste obrazow - nie rzuca wyjatku, zeby brak danych
    zrodlowych nie wywalal calego flow zapytanie -> odpowiedz.
    """
    retriever = retriever or _get_default_retriever()
    hits = retriever.retrieve(query, top_k=top_k)

    text_fragments = [_format_fragment(h) for h in hits if h.get("content_type") == "text"]
    image_paths = [h["value"] for h in hits if h.get("content_type") == "image"]

    prompt = "\n\n".join(text_fragments)
    return prompt, image_paths
