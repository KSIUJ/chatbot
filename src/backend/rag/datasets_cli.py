"""
CLI zbiorow danych zrodel (format: core/datasets.py, DATASETS.md).
Uruchamiane z katalogu glownego repo (data/ jest wzgledne).

    python -m src.backend.rag.datasets_cli convert            # stare wyjscie scraperow -> nowy format
    python -m src.backend.rag.datasets_cli convert --source usos
    python -m src.backend.rag.datasets_cli check              # sprawdzenie zbiorow i notatek KSI
    python -m src.backend.rag.datasets_cli schemas --out docs/datasets
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core.datasets import DatasetError, json_schemas, read_dataset, write_dataset
from .registry import create_sources
from .sources.ksi.dataset import NoteRecord
from .sources.ksi.notes import read_notes

DATA_DIR = Path("data")


def convert(data_dir: Path, names: list[str]) -> dict[str, int]:
    """Zapisuje zbiory z adapterow starych formatow; zrodlo bez starych danych
    jest pomijane (jego zbior zostaje bez zmian)."""
    sources = create_sources()
    summary = {}
    for name in names:
        records = sources[name].convert_legacy(data_dir)
        if records is None:
            print(f"[datasets] {name}: brak starych danych, pomijam")
            continue
        write_dataset(sources[name].dataset_dir(data_dir), name, records, collector=f"legacy:{name}")
        print(f"[datasets] {name}: zapisano {len(records)} rekordow")
        summary[name] = len(records)
    return summary


def check(data_dir: Path, names: list[str]) -> bool:
    """Sprawdza zbiory (i notatki KSI); wypisuje bledy, zwraca True gdy wszystko ok."""
    sources = create_sources()
    ok = True
    for name in names:
        source = sources[name]
        try:
            dataset = read_dataset(source.dataset_dir(data_dir), name, source.record_model)
            print(f"[datasets] {name}: {len(dataset.records) if dataset else 'brak zbioru'}")
            if name == "ksi":
                print(f"[datasets] ksi: notatki {len(read_notes(source.notes_dir))}")
        except DatasetError as error:
            ok = False
            print(f"[datasets] BLAD {error}", file=sys.stderr)
    return ok


def schemas(out_dir: Path) -> list[Path]:
    """Schematy JSON manifestu i rekordow kazdego zrodla (+ notatki KSI)."""
    models = [(name, source.record_model) for name, source in create_sources().items()]
    models.append(("ksi-note", NoteRecord))
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, schema in json_schemas(models).items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    names = list(create_sources())
    parser = argparse.ArgumentParser(description="Zbiory danych zrodel RAG-a.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("convert", "check"):
        sub = commands.add_parser(command)
        sub.add_argument("--source", choices=names, action="append", dest="sources")
        sub.add_argument("--data-dir", type=Path, default=DATA_DIR)
    sub = commands.add_parser("schemas")
    sub.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "convert":
        convert(args.data_dir, args.sources or names)
    elif args.command == "check":
        sys.exit(0 if check(args.data_dir, args.sources or names) else 1)
    else:
        for path in schemas(args.out):
            print(f"[datasets] {path}")


if __name__ == "__main__":
    main()
