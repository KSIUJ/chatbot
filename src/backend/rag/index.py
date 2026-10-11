"""
CLI indeksu RAG: budowa, aktualizacja i przelaczanie indeksow (uklad:
core/index_store.py). Uruchamiane z katalogu glownego aplikacji (data/
i dataset/ sa wzgledne; w Dockerze /app).

    python -m src.backend.rag.index build                 # nowy indeks od zera, potem przelaczenie
    python -m src.backend.rag.index build --source usos   # od zera tylko usos, reszta z biezacego
    python -m src.backend.rag.index sync                  # nowe/zmienione/usuniete dokumenty
    python -m src.backend.rag.index status
    python -m src.backend.rag.index rollback              # powrot do poprzedniego indeksu
    python -m src.backend.rag.index use 20261011T120000Z

build i sync nigdy nie zmieniaja indeksu, z ktorego korzysta backend:
pracuja na nowym katalogu dataset/indexes/<czas UTC>/ (sync zaczyna od kopii
biezacego i embeduje tylko zmienione dokumenty), a na koncu atomowo
przelaczaja dataset/CURRENT. Przerwany build/sync (np. restart maszyny)
wznawia sie przy ponownym uruchomieniu tego samego polecenia - zapisane
partie zostaja. Trzymane sa KEEP_PREVIOUS poprzednie indeksy (rollback),
starsze sa usuwane.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import shutil
import sqlite3
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .core import chunking
from .core.datasets import MANIFEST, Manifest
from .core.documents import Document
from .core.encoder import Encoder, configured_settings
from .core.index_store import (
    BUILDING_FILE,
    CHECK_INTERVAL,
    DATASET_DIR,
    FORMAT_VERSION,
    POINTER_FILE,
    embedding_mismatches,
    index_location,
    indexes_dir,
    is_complete,
    legacy_location,
    list_indexes,
    read_meta,
    read_pointer,
    write_meta,
    write_pointer,
)
from .core.lexical import LexicalIndex
from .core.vectorstore import VectorStore, document_hash

DATA_DIR = Path("data")
BATCH_SIZE = 256
# ile poprzednich (dokonczonych) indeksow zostaje obok biezacego
KEEP_PREVIOUS = 2
LOCK_FILE = ".index.lock"
# baza Chromy w katalogu vectorstore/
CHROMA_DB = "chroma.sqlite3"

Loader = Callable[[], list[Document]]


class IndexCommandError(RuntimeError):
    """Blad polecenia indeksu (komunikat dla operatora)."""


def _log(message: str) -> None:
    print(f"[index] {message}", flush=True)


@dataclass
class SyncCounts:
    added: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0

    @property
    def changed(self) -> int:
        return self.added + self.updated + self.deleted


@dataclass
class IndexResult:
    # katalog indeksu po poleceniu (nowy albo biezacy, gdy nic sie nie zmienilo)
    directory: Path
    switched: bool
    counts: dict[str, SyncCounts] = field(default_factory=dict)


class _LazyEncoder:
    """Encoder ladowany dopiero przy pierwszym embedowaniu - sync bez zmian
    i status nie laduja modelu."""

    def __init__(self) -> None:
        settings = configured_settings()
        self.model_name = settings["model"]
        self.query_prefix = settings["query_prefix"]
        self.passage_prefix = settings["passage_prefix"]
        self._encoder: Encoder | None = None

    def _get(self) -> Encoder:
        if self._encoder is None:
            self._encoder = Encoder()
        return self._encoder

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._get().embed_batch(texts)

    def embed_query(self, query: str) -> list[float]:
        return self._get().embed_query(query)


def default_loaders(data_dir: Path = DATA_DIR) -> dict[str, Loader]:
    """Zrodla z rejestru: wczytanie zbioru data/<zrodlo>/ jako dokumenty."""
    from .registry import create_sources

    return {
        name: (lambda source=source: source.load_documents(data_dir))
        for name, source in create_sources().items()
    }


# --- synchronizacja jednego zrodla -------------------------------------------------------------


def _unique(source: str, documents: list[Document]) -> list[Document]:
    foreign = sorted({d.source for d in documents} - {source})
    if foreign:
        raise ValueError(f"{source}: dokumenty innego zrodla ({', '.join(foreign)})")
    seen: dict[str, Document] = {}
    for document in documents:
        if document.id in seen:
            continue
        seen[document.id] = document
    if len(seen) != len(documents):
        _log(f"UWAGA: {source}: {len(documents) - len(seen)} powtorzonych id, zostaje pierwsze wystapienie")
    return list(seen.values())


def sync_source(
    source: str,
    documents: list[Document],
    store: VectorStore,
    lexical: LexicalIndex,
    batch_size: int = BATCH_SIZE,
) -> SyncCounts:
    """Doprowadza oba indeksy do stanu `documents` dla jednego zrodla.

    Nowe i zmienione dokumenty (inny content_hash) sa embedowane, brakujace
    w danych usuwane z obu indeksow. Kolejnosc zapisow (najpierw BM25, potem
    wektor ze skrotem) sprawia, ze przerwanie w dowolnym miejscu jest
    naprawiane przy nastepnym uruchomieniu.
    """
    documents = _unique(source, documents)
    hashes = store.source_hashes(source)
    lexical_ids = lexical.source_ids(source)
    wanted = {d.id for d in documents}

    changed = [d for d in documents if hashes.get(d.id) != document_hash(d)]
    changed_ids = {d.id for d in changed}
    counts = SyncCounts(
        added=sum(1 for d in changed if d.id not in hashes),
        updated=sum(1 for d in changed if d.id in hashes),
        unchanged=len(documents) - len(changed),
    )

    stale_vectors = sorted(set(hashes) - wanted)
    stale_lexical = sorted(lexical_ids - wanted)
    counts.deleted = len(set(stale_vectors) | set(stale_lexical))
    if stale_vectors:
        store.delete_ids(stale_vectors)
    if stale_lexical:
        lexical.delete_ids(stale_lexical)

    # wektor aktualny, a w BM25 brak wpisu (przerwany zapis) - bez embedowania
    lexical.add_documents([d for d in documents if d.id not in changed_ids and d.id not in lexical_ids])

    done = 0
    for i in range(0, len(changed), batch_size):
        batch = changed[i : i + batch_size]
        lexical.add_documents(batch)
        store.add_documents(batch)
        done += len(batch)
        _log(f"{source}: {done}/{len(changed)} zapisanych")

    _log(
        f"{source}: dodane {counts.added}, zmienione {counts.updated}, "
        f"usuniete {counts.deleted}, bez zmian {counts.unchanged}"
    )
    return counts


# --- katalogi indeksow -------------------------------------------------------------------------


@contextmanager
def _locked(dataset_dir: Path) -> Iterator[None]:
    """Jeden build/sync naraz (blokada pliku, zwalniana takze po zabiciu procesu)."""
    dataset_dir.mkdir(parents=True, exist_ok=True)
    with (dataset_dir / LOCK_FILE).open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise IndexCommandError("inny build/sync indeksu juz dziala") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_directory(dataset_dir: Path, moment: datetime) -> Path:
    root = indexes_dir(dataset_dir)
    root.mkdir(parents=True, exist_ok=True)
    base = moment.strftime("%Y%m%dT%H%M%SZ")
    directory, n = root / base, 1
    while directory.exists():
        n += 1
        directory = root / f"{base}-{n}"
    directory.mkdir()
    return directory


def _read_marker(directory: Path) -> dict | None:
    try:
        marker = json.loads((directory / BUILDING_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return marker if isinstance(marker, dict) else None


def _write_marker(directory: Path, marker: dict) -> None:
    (directory / BUILDING_FILE).write_text(json.dumps(marker, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_sqlite(source: Path, target: Path) -> None:
    """Spojna kopia bazy SQLite (backup API - takze gdy inny proces ja otworzyl)."""
    con, out = sqlite3.connect(source), sqlite3.connect(target)
    try:
        con.backup(out)
    finally:
        out.close()
        con.close()


def _copy_index(source: Path, target: Path) -> None:
    """Kopia indeksu (wektory + BM25). Do katalogu indeksu pisze tylko CLI pod
    blokada; bazy SQLite (Chroma zapisuje swoja takze przy otwarciu przez
    backend) kopiowane przez backup API."""
    src, dst = index_location(source), index_location(target)
    shutil.copytree(src.vectorstore, dst.vectorstore, ignore=shutil.ignore_patterns(f"{CHROMA_DB}*"))
    _copy_sqlite(src.vectorstore / CHROMA_DB, dst.vectorstore / CHROMA_DB)
    _copy_sqlite(src.lexical, dst.lexical)


def _start(dataset_dir: Path, plan: dict, moment: datetime) -> tuple[Path, bool]:
    """Katalog do pracy: wznowiony niedokonczony o tym samym planie albo nowy
    (z kopia indeksu bazowego). Inne niedokonczone katalogi sa usuwane.
    Zwraca (katalog, czy nowy)."""
    resumed: Path | None = None
    for directory in reversed(list_indexes(dataset_dir)):
        if not (directory / BUILDING_FILE).exists():
            continue
        marker = _read_marker(directory) or {}
        prepared = marker.pop("prepared", False)
        if resumed is None and prepared and marker == plan:
            resumed = directory
            _log(f"wznawiam niedokonczony indeks {directory.name}")
        else:
            _log(f"usuwam niedokonczony indeks {directory.name}")
            shutil.rmtree(directory)
    if resumed is not None:
        return resumed, False

    directory = _new_directory(dataset_dir, moment)
    _write_marker(directory, {**plan, "prepared": False})
    if plan.get("base"):
        _log(f"kopiuje indeks {plan['base']} do {directory.name}")
        _copy_index(indexes_dir(dataset_dir) / plan["base"], directory)
    return directory, True


def _mark_prepared(directory: Path, plan: dict) -> None:
    _write_marker(directory, {**plan, "prepared": True})


def dataset_info(data_dir: Path, source: str) -> dict | None:
    """collected_at/collector z data/<zrodlo>/manifest.json (None bez manifestu)."""
    path = data_dir / source / MANIFEST
    try:
        manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"collected_at": _iso(manifest.collected_at.astimezone(timezone.utc)), "collector": manifest.collector}


def _finish(
    dataset_dir: Path,
    directory: Path,
    store: VectorStore,
    lexical: LexicalIndex,
    *,
    kind: str,
    base: dict | None,
    processed: Mapping[str, SyncCounts],
    data_dir: Path,
    moment: datetime,
    keep: int,
) -> None:
    """meta.json, zdjecie znacznika, przelaczenie CURRENT i sprzatanie."""
    vectors, lexical_counts = store.source_counts(), lexical.source_counts()
    base_sources = (base or {}).get("sources") or {}
    sources = {}
    for name in sorted(set(vectors) | set(lexical_counts) | set(processed)):
        previous = base_sources.get(name) or {}
        entry = {
            "documents": vectors.get(name, 0),
            "lexical": lexical_counts.get(name, 0),
            "dataset": previous.get("dataset"),
            "indexed_at": previous.get("indexed_at"),
            "last_change": previous.get("last_change"),
        }
        if name in processed:
            entry.update(
                dataset=dataset_info(data_dir, name),
                indexed_at=_iso(moment),
                last_change=asdict(processed[name]),
            )
        sources[name] = entry

    meta = {
        "format_version": FORMAT_VERSION,
        "created_at": _iso(moment),
        "kind": kind,
        "base": (base or {}).get("name"),
        "embedding": configured_settings(),
        "chunking": {"chunk_size": chunking.CHUNK_SIZE, "chunk_overlap": chunking.CHUNK_OVERLAP},
        "documents": sum(vectors.values()),
        "sources": sources,
    }
    store.close()
    lexical.close()
    write_meta(directory, meta)
    (directory / BUILDING_FILE).unlink()
    write_pointer(dataset_dir, directory)
    _log(f"biezacy indeks: {directory.name} ({meta['documents']} dokumentow)")
    prune(dataset_dir, keep)


def prune(dataset_dir: Path, keep: int = KEEP_PREVIOUS) -> list[str]:
    """Usuwa dokonczone indeksy poza biezacym i `keep` najnowszymi pozostalymi."""
    current = read_pointer(dataset_dir)
    others = [d for d in list_indexes(dataset_dir) if is_complete(d) and d != current]
    removed = []
    for directory in others[: max(0, len(others) - keep)]:
        shutil.rmtree(directory)
        removed.append(directory.name)
        _log(f"usunieto stary indeks {directory.name}")
    return removed


def _current(dataset_dir: Path) -> tuple[Path | None, dict | None]:
    directory = read_pointer(dataset_dir)
    return directory, (read_meta(directory) if directory is not None else None)


def _require_compatible(meta: dict | None, what: str) -> None:
    problems = embedding_mismatches(meta, configured_settings())
    if problems:
        raise IndexCommandError(
            f"biezacy indeks zbudowano inaczej niz obecna konfiguracja ({'; '.join(problems)}) - "
            f"{what} pomieszaloby wektory; uzyj pelnego build"
        )


def _open_stores(directory: Path, encoder) -> tuple[VectorStore, LexicalIndex]:
    location = index_location(directory)
    return VectorStore(persist_dir=str(location.vectorstore), encoder=encoder), LexicalIndex(str(location.lexical))


# --- polecenia ---------------------------------------------------------------------------------


def build(
    sources: list[str] | None = None,
    *,
    dataset_dir: Path = DATASET_DIR,
    data_dir: Path = DATA_DIR,
    loaders: Mapping[str, Loader] | None = None,
    encoder=None,
    batch_size: int = BATCH_SIZE,
    keep: int = KEEP_PREVIOUS,
    now: Callable[[], datetime] = _now,
) -> IndexResult:
    """Nowy indeks: wybrane zrodla (domyslnie wszystkie) od zera, pozostale
    skopiowane z biezacego; potem przelaczenie CURRENT."""
    loaders = loaders if loaders is not None else default_loaders(data_dir)
    unknown = sorted(set(sources or ()) - set(loaders))
    if unknown:
        raise IndexCommandError(f"nieznane zrodla: {', '.join(unknown)}")
    rebuilt = sorted(set(sources)) if sources else sorted(loaders)

    with _locked(dataset_dir):
        current, current_meta = _current(dataset_dir)
        partial = bool(sources) and set(rebuilt) != set(loaders)
        base = current.name if partial and current is not None else None
        if partial and current is None:
            _log("UWAGA: brak biezacego indeksu - nowy bedzie mial tylko wybrane zrodla")
        if base:
            _require_compatible(current_meta, "build czesci zrodel")

        plan = {"kind": "build", "base": base, "sources": rebuilt, "embedding": configured_settings()}
        moment = now()
        directory, fresh = _start(dataset_dir, plan, moment)
        store, lexical = _open_stores(directory, encoder or _LazyEncoder())

        documents = {}
        for name in rebuilt:
            documents[name] = loaders[name]()
            if not documents[name]:
                _log(f"UWAGA: {name}: brak dokumentow (brak zbioru w data/{name}/?)")
        if fresh:
            for name in rebuilt:
                # zrodlo bez danych zostaje takie, jak w biezacym indeksie
                if base and documents[name]:
                    store.delete_source(name)
                    lexical.delete_source(name)
            _mark_prepared(directory, plan)

        counts = {
            name: sync_source(name, docs, store, lexical, batch_size)
            for name, docs in documents.items()
            if docs
        }
        base_meta = {**current_meta, "name": base} if base and current_meta else None
        _finish(
            dataset_dir, directory, store, lexical,
            kind="build", base=base_meta, processed=counts, data_dir=data_dir, moment=moment, keep=keep,
        )
        return IndexResult(directory, True, counts)


def sync(
    sources: list[str] | None = None,
    *,
    dataset_dir: Path = DATASET_DIR,
    data_dir: Path = DATA_DIR,
    loaders: Mapping[str, Loader] | None = None,
    encoder=None,
    batch_size: int = BATCH_SIZE,
    keep: int = KEEP_PREVIOUS,
    now: Callable[[], datetime] = _now,
) -> IndexResult:
    """Aktualizacja biezacego indeksu: kopia + nowe/zmienione/usuniete dokumenty
    wybranych zrodel, potem przelaczenie. Bez zmian - indeks zostaje ten sam.
    Bez biezacego indeksu robi pelny build."""
    loaders = loaders if loaders is not None else default_loaders(data_dir)
    unknown = sorted(set(sources or ()) - set(loaders))
    if unknown:
        raise IndexCommandError(f"nieznane zrodla: {', '.join(unknown)}")
    selected = sorted(set(sources)) if sources else sorted(loaders)

    current, current_meta = _current(dataset_dir)
    if current is None:
        _log("brak biezacego indeksu (dataset/CURRENT) - buduje nowy")
        return build(
            dataset_dir=dataset_dir, data_dir=data_dir, loaders=loaders, encoder=encoder,
            batch_size=batch_size, keep=keep, now=now,
        )

    with _locked(dataset_dir):
        current, current_meta = _current(dataset_dir)
        assert current is not None
        _require_compatible(current_meta, "sync")
        plan = {"kind": "sync", "base": current.name, "sources": selected, "embedding": configured_settings()}
        moment = now()
        directory, fresh = _start(dataset_dir, plan, moment)
        if fresh:
            _mark_prepared(directory, plan)
        store, lexical = _open_stores(directory, encoder or _LazyEncoder())

        counts: dict[str, SyncCounts] = {}
        for name in selected:
            documents = loaders[name]()
            if not documents:
                _log(f"UWAGA: {name}: brak dokumentow, pomijam (dane w indeksie bez zmian)")
                continue
            counts[name] = sync_source(name, documents, store, lexical, batch_size)

        if not fresh:
            # wznowiony: czesc zmian zapisano przed przerwaniem, liczby ich nie obejmuja
            _log("wznowiony sync - liczby obejmuja tylko zmiany od wznowienia")
        elif not any(c.changed for c in counts.values()):
            store.close()
            lexical.close()
            shutil.rmtree(directory)
            _refresh_dataset_info(current, current_meta, counts, data_dir)
            _log(f"bez zmian - zostaje indeks {current.name}")
            return IndexResult(current, False, counts)

        _finish(
            dataset_dir, directory, store, lexical,
            kind="sync", base={**(current_meta or {}), "name": current.name},
            processed=counts, data_dir=data_dir, moment=moment, keep=keep,
        )
        return IndexResult(directory, True, counts)


def _refresh_dataset_info(directory: Path, meta: dict | None, counts: Mapping[str, SyncCounts], data_dir: Path) -> None:
    """Sync bez zmian w dokumentach: nowsze dane zrodla (manifest) odnotowane
    w meta.json biezacego indeksu."""
    if meta is None:
        return
    changed = False
    for name in counts:
        entry = (meta.get("sources") or {}).get(name)
        info = dataset_info(data_dir, name)
        if entry is not None and info is not None and entry.get("dataset") != info:
            entry["dataset"] = info
            changed = True
    if changed:
        write_meta(directory, meta)


def use(name: str, *, dataset_dir: Path = DATASET_DIR) -> Path:
    """Przelacza CURRENT na wskazany dokonczony indeks."""
    directory = indexes_dir(dataset_dir) / name
    if Path(name).name != name or not is_complete(directory):
        available = ", ".join(d.name for d in list_indexes(dataset_dir) if is_complete(d)) or "brak"
        raise IndexCommandError(f"nie ma dokonczonego indeksu {name!r} (dostepne: {available})")
    with _locked(dataset_dir):
        write_pointer(dataset_dir, directory)
    _log(f"biezacy indeks: {name}")
    return directory


def rollback(*, dataset_dir: Path = DATASET_DIR) -> Path:
    """Powrot do najnowszego dokonczonego indeksu starszego niz biezacy."""
    current = read_pointer(dataset_dir)
    older = [d for d in list_indexes(dataset_dir) if is_complete(d) and (current is None or d.name < current.name)]
    if not older:
        raise IndexCommandError("nie ma starszego indeksu do przywrocenia")
    return use(older[-1].name, dataset_dir=dataset_dir)


def status(*, dataset_dir: Path = DATASET_DIR) -> dict:
    """Stan indeksu: biezacy katalog, meta.json, liczby w obu indeksach,
    ostrzezenia o niezgodnosciach i lista katalogow."""
    current = read_pointer(dataset_dir)
    pointer_exists = (dataset_dir / POINTER_FILE).exists()
    location = index_location(current) if current is not None else legacy_location(dataset_dir)
    meta = read_meta(current) if current is not None else None
    warnings: list[str] = []
    if pointer_exists and current is None:
        warnings.append(f"{POINTER_FILE} wskazuje niepoprawny albo niedokonczony indeks - uzywany stary uklad")

    vectors: dict[str, int] = {}
    lexical: dict[str, int] = {}
    if (location.vectorstore / CHROMA_DB).is_file():
        store = VectorStore(persist_dir=str(location.vectorstore), encoder=_LazyEncoder())
        vectors = store.source_counts()
        store.close()
    else:
        warnings.append("brak indeksu wektorowego")
    if location.lexical.is_file():
        index = LexicalIndex(str(location.lexical))
        lexical = index.source_counts()
        index.close()
    else:
        warnings.append("brak indeksu BM25")

    for name in sorted(set(vectors) | set(lexical)):
        if vectors.get(name, 0) != lexical.get(name, 0):
            warnings.append(f"{name}: wektory {vectors.get(name, 0)}, BM25 {lexical.get(name, 0)}")
    if meta is not None:
        warnings += [f"embedding {p}" for p in embedding_mismatches(meta, configured_settings())]
        chunks = {"chunk_size": chunking.CHUNK_SIZE, "chunk_overlap": chunking.CHUNK_OVERLAP}
        if meta.get("chunking") != chunks:
            warnings.append(f"chunking: indeks {meta.get('chunking')}, kod {chunks} - zrob build")
        for name, entry in (meta.get("sources") or {}).items():
            if entry.get("documents") != vectors.get(name, 0):
                warnings.append(f"{name}: meta.json {entry.get('documents')}, w indeksie {vectors.get(name, 0)}")
    elif current is None and (vectors or lexical):
        warnings.append("stary uklad bez meta.json - zbuduj indeks: python -m src.backend.rag.index build")

    return {
        "current": current.name if current is not None else None,
        "meta": meta,
        "vectors": vectors,
        "lexical": lexical,
        "warnings": warnings,
        "indexes": [
            {"name": d.name, "complete": is_complete(d), "current": d == current}
            for d in list_indexes(dataset_dir)
        ],
        "check_interval_seconds": CHECK_INTERVAL,
    }


def _print_status(report: dict) -> None:
    meta = report["meta"] or {}
    print(f"Biezacy indeks: {report['current'] or 'stary uklad (dataset/vectorstore + dataset/lexical.db)'}")
    if meta:
        print(f"  zbudowany: {meta.get('created_at')} ({meta.get('kind')}, baza: {meta.get('base') or '-'})")
        embedding = meta.get("embedding") or {}
        print(
            f"  embedding: {embedding.get('model')}  prefiksy: zapytanie={embedding.get('query_prefix')!r} "
            f"dokument={embedding.get('passage_prefix')!r}"
        )
        print(f"  chunking: {meta.get('chunking')}")
    sources = meta.get("sources") or {}
    names = sorted(set(report["vectors"]) | set(report["lexical"]) | set(sources))
    if names:
        print(f"  {'zrodlo':<10} {'wektory':>8} {'BM25':>8}  dane zebrane")
        for name in names:
            dataset = (sources.get(name) or {}).get("dataset") or {}
            print(
                f"  {name:<10} {report['vectors'].get(name, 0):>8} {report['lexical'].get(name, 0):>8}  "
                f"{dataset.get('collected_at', '-')} {dataset.get('collector', '')}".rstrip()
            )
    if report["indexes"]:
        print("Katalogi dataset/indexes/:")
        for entry in report["indexes"]:
            state = "biezacy" if entry["current"] else ("gotowy" if entry["complete"] else "niedokonczony")
            print(f"  {entry['name']}  {state}")
    for warning in report["warnings"]:
        print(f"UWAGA: {warning}")


def _print_counts(result: IndexResult) -> None:
    total = SyncCounts()
    for counts in result.counts.values():
        for key in ("added", "updated", "deleted", "unchanged"):
            setattr(total, key, getattr(total, key) + getattr(counts, key))
    _log(
        f"razem: dodane {total.added}, zmienione {total.updated}, usuniete {total.deleted}, "
        f"bez zmian {total.unchanged}; indeks {result.directory.name}"
        + ("" if result.switched else " (bez przelaczenia)")
    )


def main(argv: list[str] | None = None) -> int:
    from .registry import create_sources

    names = list(create_sources())
    parser = argparse.ArgumentParser(prog="python -m src.backend.rag.index", description="Indeks RAG.")
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("build", "nowy indeks od zera (z --source: tylko te zrodla, reszta z biezacego)"),
        ("sync", "nowe, zmienione i usuniete dokumenty wzgledem biezacego indeksu"),
    ):
        sub = commands.add_parser(command, help=help_text)
        sub.add_argument("--source", choices=names, action="append", dest="sources")
        sub.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    commands.add_parser("status", help="biezacy indeks, liczby, niezgodnosci").add_argument(
        "--json", action="store_true"
    )
    commands.add_parser("rollback", help="powrot do poprzedniego indeksu")
    commands.add_parser("use", help="przelaczenie na wskazany indeks").add_argument("name")
    args = parser.parse_args(argv)

    try:
        if args.command in ("build", "sync"):
            command = build if args.command == "build" else sync
            result = command(
                args.sources, dataset_dir=args.dataset_dir, data_dir=args.data_dir, batch_size=args.batch_size
            )
            _print_counts(result)
        elif args.command == "status":
            report = status(dataset_dir=args.dataset_dir)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                _print_status(report)
        elif args.command == "rollback":
            rollback(dataset_dir=args.dataset_dir)
        else:
            use(args.name, dataset_dir=args.dataset_dir)
    except IndexCommandError as error:
        print(f"[index] BLAD: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
