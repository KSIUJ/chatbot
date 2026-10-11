"""
Zgodnosc wstecz: stare polecenie ingestu przekierowane na CLI indeksu
(src/backend/rag/index.py), ktore buduje indeks w nowym katalogu
i atomowo go przelacza.

    python -m pipeline.ingest.run_ingest                     -> index sync
    python -m pipeline.ingest.run_ingest --source usos       -> index sync --source usos
    python -m pipeline.ingest.run_ingest --source usos --purge -> index build --source usos
    python -m pipeline.ingest.run_ingest --purge             -> index build
    python -m pipeline.ingest.run_ingest --rebuild-lexical   -> index build (BM25 powstaje razem z wektorami)
"""

from __future__ import annotations

import argparse
import sys

from src.backend.rag.index import main as index_main


def index_args(argv: list[str] | None = None) -> list[str]:
    """Argumenty CLI indeksu odpowiadajace staremu wywolaniu run_ingest."""
    parser = argparse.ArgumentParser(description="Przestarzale - uzyj: python -m src.backend.rag.index")
    parser.add_argument("--source", action="append", dest="sources", default=[])
    parser.add_argument("--purge", action="store_true")
    parser.add_argument("--rebuild-lexical", action="store_true")
    args = parser.parse_args(argv)

    command = "build" if args.purge or args.rebuild_lexical else "sync"
    result = [command]
    if not args.rebuild_lexical:
        for source in args.sources:
            result += ["--source", source]
    return result


def main(argv: list[str] | None = None) -> int:
    args = index_args(argv)
    print(f"[ingest] przestarzale - uruchamiam: python -m src.backend.rag.index {' '.join(args)}", flush=True)
    return index_main(args)


if __name__ == "__main__":
    sys.exit(main())
