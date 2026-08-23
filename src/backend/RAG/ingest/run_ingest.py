"""
CLI: uruchamia ingest wszystkich trzech zrodel danych i zapisuje je do
wspolnego vectorstore (patrz src/backend/RAG/vectorstore.py).

Uzycie:
    python -m src.backend.RAG.ingest.run_ingest
    python -m src.backend.RAG.ingest.run_ingest --source mordor
"""

import argparse

from . import from_mordor, from_strony, from_usos

SOURCE_LOADERS = {
    "mordor": from_mordor.load_documents,
    "strony": from_strony.load_documents,
    "usos": from_usos.load_documents,
}


def run_ingest(sources: list[str] | None = None) -> dict[str, int]:
    """Wczytuje dokumenty z wybranych zrodel (domyslnie wszystkich) i dodaje
    je do vectorstore. Zwraca liczbe dokumentow dodanych per zrodlo."""
    from ..vectorstore import VectorStore

    sources = sources or list(SOURCE_LOADERS.keys())
    store = VectorStore()
    summary = {}

    for source in sources:
        loader = SOURCE_LOADERS[source]
        documents = loader()
        if documents:
            store.add_documents(documents)
        summary[source] = len(documents)
        print(f"[ingest] {source}: {len(documents)} dokumentow")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest danych do vectorstore RAG.")
    parser.add_argument(
        "--source",
        choices=list(SOURCE_LOADERS.keys()),
        action="append",
        dest="sources",
        help="Ograniczenie ingestu do wybranego zrodla (mozna podac wielokrotnie). "
        "Domyslnie: wszystkie zrodla.",
    )
    args = parser.parse_args()

    summary = run_ingest(args.sources)
    total = sum(summary.values())
    print(f"[ingest] Razem dodano {total} dokumentow.")


if __name__ == "__main__":
    main()
