"""
Uklad indeksow RAG w dataset/.

Kazdy zbudowany indeks ma wlasny katalog dataset/indexes/<czas UTC>/
(vectorstore/, lexical.db, meta.json), a plik dataset/CURRENT wskazuje
biezacy - zapis przez rename, wiec przelaczenie jest atomowe, a powrot do
poprzedniego indeksu to zmiana wskaznika. Bez CURRENT obowiazuje stary
uklad (dataset/vectorstore + dataset/lexical.db), zeby dzialajacy indeks
nie przestal byc widoczny przed pierwszym buildem.

Indeksy buduje i aktualizuje src/backend/rag/index.py; VectorStore
i LexicalIndex bez jawnej sciezki czytaja indeks wskazany przez CURRENT
i zauwazaja zmiane wskaznika (sprawdzenie najwyzej co CHECK_INTERVAL s).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DATASET_DIR = Path("dataset")
INDEXES_DIR = "indexes"
POINTER_FILE = "CURRENT"
META_FILE = "meta.json"
# znacznik niedokonczonego indeksu (build/sync przerwany albo w toku)
BUILDING_FILE = "BUILDING"
VECTORSTORE_DIR = "vectorstore"
LEXICAL_DB = "lexical.db"
# wersja ukladu katalogu indeksu i meta.json
FORMAT_VERSION = 1
# co ile sekund backend sprawdza, czy CURRENT wskazuje inny indeks
CHECK_INTERVAL = 10.0


@dataclass(frozen=True)
class IndexLocation:
    vectorstore: Path
    lexical: Path
    # katalog indeksu; None = stary uklad bez wskaznika
    directory: Path | None = None

    @property
    def name(self) -> str | None:
        return self.directory.name if self.directory is not None else None

    def meta(self) -> dict | None:
        return read_meta(self.directory) if self.directory is not None else None


def index_location(directory: Path) -> IndexLocation:
    return IndexLocation(directory / VECTORSTORE_DIR, directory / LEXICAL_DB, directory)


def legacy_location(dataset_dir: Path = DATASET_DIR) -> IndexLocation:
    return IndexLocation(dataset_dir / VECTORSTORE_DIR, dataset_dir / LEXICAL_DB)


def indexes_dir(dataset_dir: Path = DATASET_DIR) -> Path:
    return dataset_dir / INDEXES_DIR


def read_meta(directory: Path) -> dict | None:
    """meta.json indeksu; None, gdy go nie ma albo jest nieczytelny."""
    try:
        meta = json.loads((directory / META_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def _write_atomic(path: Path, text: str) -> None:
    """Zapis przez plik tymczasowy i rename (czytelnik widzi stara albo nowa tresc)."""
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as out:
        out.write(text)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)
    try:
        fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_meta(directory: Path, meta: dict) -> None:
    _write_atomic(directory / META_FILE, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")


def is_complete(directory: Path) -> bool:
    """Indeks dokonczony: ma meta.json i nie ma znacznika BUILDING."""
    return (directory / META_FILE).is_file() and not (directory / BUILDING_FILE).exists()


def list_indexes(dataset_dir: Path = DATASET_DIR) -> list[Path]:
    """Katalogi indeksow od najstarszego (nazwy to czas UTC)."""
    root = indexes_dir(dataset_dir)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def read_pointer(dataset_dir: Path = DATASET_DIR) -> Path | None:
    """Katalog wskazany przez CURRENT; None bez wskaznika albo gdy wskazuje
    cos innego niz dokonczony indeks w dataset/indexes/ (z ostrzezeniem)."""
    pointer = dataset_dir / POINTER_FILE
    try:
        target = pointer.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as error:
        logger.warning("rag index: nie mozna odczytac %s: %s", pointer, error)
        return None
    parts = Path(target).parts
    if len(parts) != 2 or parts[0] != INDEXES_DIR or parts[1] in ("", ".", ".."):
        logger.warning("rag index: %s wskazuje niepoprawne miejsce %r - pomijam", pointer, target)
        return None
    directory = dataset_dir / target
    if not is_complete(directory):
        logger.warning("rag index: %s wskazuje niekompletny indeks %r - pomijam", pointer, target)
        return None
    return directory


def write_pointer(dataset_dir: Path, directory: Path) -> None:
    """Atomowo przelacza CURRENT na dokonczony indeks z dataset/indexes/."""
    if directory.parent.resolve() != indexes_dir(dataset_dir).resolve():
        raise ValueError(f"{directory} nie lezy w {indexes_dir(dataset_dir)}")
    if not is_complete(directory):
        raise ValueError(f"indeks {directory.name} nie jest dokonczony")
    _write_atomic(dataset_dir / POINTER_FILE, f"{INDEXES_DIR}/{directory.name}\n")


def resolve(dataset_dir: Path = DATASET_DIR) -> IndexLocation:
    """Biezacy indeks: wskazany przez CURRENT albo stary uklad."""
    directory = read_pointer(dataset_dir)
    return index_location(directory) if directory is not None else legacy_location(dataset_dir)


def embedding_mismatches(meta: dict | None, settings: dict[str, str] | None) -> list[str]:
    """Roznice miedzy modelem/prefiksami, ktorymi zbudowano indeks (meta.json),
    a tymi, ktorymi koduje sie zapytania. Pusto, gdy nie ma czego porownac."""
    if meta is None or settings is None:
        return []
    problems = []
    version = meta.get("format_version")
    if version != FORMAT_VERSION:
        problems.append(f"format indeksu {version!r}, obslugiwany {FORMAT_VERSION}")
    built = meta.get("embedding") or {}
    for key, value in settings.items():
        if built.get(key) != value:
            problems.append(f"{key}: indeks {built.get(key)!r}, konfiguracja {value!r}")
    return problems


def warn_on_mismatch(location: IndexLocation, settings: dict[str, str] | None) -> list[str]:
    """Loguje ostrzezenie, gdy indeks zbudowano innym modelem/prefiksami.
    Nie przerywa pracy - wyniki wyszukiwania sa wtedy po prostu gorsze."""
    if location.directory is None:
        return []
    meta = location.meta()
    if meta is None:
        problems = ["brak meta.json"]
    else:
        problems = embedding_mismatches(meta, settings)
    if problems:
        logger.warning(
            "rag index %s niezgodny z konfiguracja (%s) - zbuduj nowy: python -m src.backend.rag.index build",
            location.name,
            "; ".join(problems),
        )
    return problems


class LocationWatch:
    """Biezacy indeks dla backendu: CURRENT czytany najwyzej co `interval` s."""

    def __init__(
        self,
        dataset_dir: Path = DATASET_DIR,
        interval: float | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.dataset_dir = dataset_dir
        self._interval = CHECK_INTERVAL if interval is None else interval
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._location = resolve(dataset_dir)
        self._next_check = monotonic() + self._interval

    def current(self) -> IndexLocation:
        now = self._monotonic()
        if now < self._next_check:
            return self._location
        with self._lock:
            if now >= self._next_check:
                self._location = resolve(self.dataset_dir)
                self._next_check = now + self._interval
            return self._location
