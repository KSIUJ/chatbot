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
    sources: list[str] | None = None, batch_size: int = BATCH_SIZE, purge: bool = False
) -> dict[str, int]:
    from ..lexical import LexicalIndex
    from ..vectorstore import VectorStore

    sources = sources or list(SOURCE_LOADERS.keys())
    store = VectorStore()
    lexical = LexicalIndex()
    summary = {}

    for source in sources:
        if purge:
            removed = store.delete_source(source)
            removed_lex = lexical.delete_source(source)
            print(f"[ingest] {source}: usunieto {removed} z vectorstore, {removed_lex} z indeksu FTS")

        loader = SOURCE_LOADERS[source]
        documents = loader()
        total = len(documents)

        todo = documents if purge else store.filter_new(documents)
        skipped = total - len(todo)
        if skipped:
            print(f"[ingest] {source}: pomijam {skipped} juz zapisanych, do zrobienia {len(todo)}")

        done = 0
        for i in range(0, len(todo), batch_size):
            batch = todo[i : i + batch_size]
            store.add_documents(batch)
            lexical.add_documents(batch)
            done += len(batch)
            print(f"[ingest] {source}: {done}/{len(todo)} zapisanych (partia {i // batch_size + 1})")

        summary[source] = total
        print(f"[ingest] {source}: {total} dokumentow lacznie (nowych {len(todo)}, juz bylo {skipped})")

    return summary


def rebuild_lexical(batch_size: int = 5000) -> int:
    from ..lexical import LexicalIndex
    from ..vectorstore import VectorStore

    collection = VectorStore().collection
    lexical = LexicalIndex()

    done = 0
    while True:
        batch = collection.get(
            limit=batch_size, offset=done, include=["documents", "metadatas"]
        )
        if not batch["ids"]:
            break

        lexical.add_raw(
            [
                (doc_id, (metadata or {}).get("source"), text or "")
                for doc_id, text, metadata in zip(
                    batch["ids"], batch["documents"], batch["metadatas"]
                )
            ]
        )
        done += len(batch["ids"])
        print(f"[lexical] {done} chunkow zaindeksowanych")

    return done


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
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Usuwa dane zrodla z obu indeksow przed ingestem (wymusza nadpisanie zmienionych rekordow).",
    )
    parser.add_argument(
        "--rebuild-lexical",
        action="store_true",
        help="Odbudowuje indeks leksykalny (FTS5) z istniejacego vectorstore i konczy.",
    )
    args = parser.parse_args()

    if args.rebuild_lexical:
        total = rebuild_lexical()
        print(f"[lexical] Gotowe: {total} chunkow.")
        return

    summary = run_ingest(args.sources, purge=args.purge)
    total = sum(summary.values())
    print(f"[ingest] Razem dodano {total} dokumentow.")


if __name__ == "__main__":
    main()
