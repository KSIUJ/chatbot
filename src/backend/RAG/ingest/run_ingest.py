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


BATCH_SIZE = 256


def run_ingest(
    sources: list[str] | None = None, batch_size: int = BATCH_SIZE
) -> dict[str, int]:
    from ..vectorstore import VectorStore

    sources = sources or list(SOURCE_LOADERS.keys())
    store = VectorStore()
    summary = {}

    for source in sources:
        loader = SOURCE_LOADERS[source]
        documents = loader()
        total = len(documents)

        todo = store.filter_new(documents)
        skipped = total - len(todo)
        if skipped:
            print(f"[ingest] {source}: pomijam {skipped} juz zapisanych, do zrobienia {len(todo)}")

        done = 0
        for i in range(0, len(todo), batch_size):
            batch = todo[i : i + batch_size]
            store.add_documents(batch) 
            done += len(batch)
            print(f"[ingest] {source}: {done}/{len(todo)} zapisanych (partia {i // batch_size + 1})")

        summary[source] = total
        print(f"[ingest] {source}: {total} dokumentow lacznie (nowych {len(todo)}, juz bylo {skipped})")

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
