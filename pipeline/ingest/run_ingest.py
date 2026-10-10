"""
CLI: ingest zrodel danych z rejestru RAG-a (src/backend/rag/registry.py) do
wspolnego vectorstore i indeksu leksykalnego. Uruchamiane z katalogu glownego
repo (sciezki data/ i dataset/ sa wzgledne).

Uzycie:
    python -m pipeline.ingest.run_ingest
    python -m pipeline.ingest.run_ingest --source mordor
    python -m pipeline.ingest.run_ingest --source usos --purge
    python -m pipeline.ingest.run_ingest --rebuild-lexical
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from src.backend.rag.core.documents import Document
from src.backend.rag.registry import create_sources
from src.backend.rag.sources.base import RagSource

if TYPE_CHECKING:
    from src.backend.rag.core.lexical import LexicalIndex
    from src.backend.rag.core.vectorstore import VectorStore

Loader = Callable[[], list[Document]]

DATA_DIR = Path("data")


def _loader(source: RagSource) -> Loader:
    return lambda: source.load_documents(DATA_DIR)


# zrodlo z rejestru -> wczytanie jego zbioru z data/<zrodlo>/ (format: rag/DATASETS.md;
# stare wyjscie scraperow najpierw: python -m src.backend.rag.datasets_cli convert)
SOURCE_LOADERS: dict[str, Loader] = {name: _loader(source) for name, source in create_sources().items()}

BATCH_SIZE = 256


def _ingest_source(
    source: str,
    documents: list[Document],
    store: VectorStore,
    lexical: LexicalIndex,
    batch_size: int,
    purge: bool,
) -> int:
    """Zapisuje dokumenty jednego zrodla; zwraca liczbe faktycznie dodanych."""
    foreign = sorted({d.source for d in documents} - {source})
    if foreign:
        raise ValueError(f"{source}: dokumenty innego zrodla ({', '.join(foreign)})")
    if purge:
        removed = store.delete_source(source)
        removed_lex = lexical.delete_source(source)
        print(f"[ingest] {source}: usunieto {removed} z vectorstore, {removed_lex} z indeksu FTS")

    todo = documents if purge else store.filter_new(documents)
    skipped = len(documents) - len(todo)
    if skipped:
        print(f"[ingest] {source}: pomijam {skipped} juz zapisanych, do zrobienia {len(todo)}")

    done = 0
    for i in range(0, len(todo), batch_size):
        batch = todo[i : i + batch_size]
        store.add_documents(batch)
        lexical.add_documents(batch)
        done += len(batch)
        print(f"[ingest] {source}: {done}/{len(todo)} zapisanych (partia {i // batch_size + 1})")

    print(f"[ingest] {source}: dodano {done} z {len(documents)} dokumentow (juz bylo {skipped})")
    return done


def run_ingest(
    sources: list[str] | None = None,
    batch_size: int = BATCH_SIZE,
    purge: bool = False,
    store: VectorStore | None = None,
    lexical: LexicalIndex | None = None,
    loaders: dict[str, Loader] | None = None,
) -> dict[str, int]:
    """Ingest wybranych zrodel (domyslnie wszystkich); zwraca {zrodlo: liczba dodanych}.

    Zrodlo, ktorego loader nie zwrocil dokumentow (np. brak pliku z danymi),
    jest pomijane - takze przy purge jego dotychczasowe dane zostaja.
    """
    loaders = loaders or SOURCE_LOADERS
    if store is None:
        from src.backend.rag.core.vectorstore import VectorStore

        store = VectorStore()
    if lexical is None:
        from src.backend.rag.core.lexical import LexicalIndex

        lexical = LexicalIndex()

    summary: dict[str, int] = {}
    for source in sources or list(loaders):
        documents = loaders[source]()
        if not documents:
            print(f"[ingest] UWAGA: {source}: brak dokumentow, pomijam (istniejace dane bez zmian)")
            summary[source] = 0
            continue
        summary[source] = _ingest_source(source, documents, store, lexical, batch_size, purge)

    return summary


def rebuild_lexical(batch_size: int = 5000) -> int:
    """Odbudowuje indeks leksykalny z tresci zapisanych w vectorstore."""
    from src.backend.rag.core.lexical import LexicalIndex
    from src.backend.rag.core.vectorstore import VectorStore

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
        choices=list(SOURCE_LOADERS),
        action="append",
        dest="sources",
        help="Ograniczenie ingestu do wybranego zrodla (mozna podac wielokrotnie). "
        "Domyslnie: wszystkie zrodla.",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Usuwa dane zrodla z obu indeksow przed zapisem (wymusza nadpisanie "
        "zmienionych rekordow). Zrodlo bez danych do wczytania nie jest czyszczone.",
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
    print(f"[ingest] Razem dodano {sum(summary.values())} dokumentow.")


if __name__ == "__main__":
    main()
