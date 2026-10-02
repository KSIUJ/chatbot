"""Diagnostyka dla panelu administratora: model (dostawca, nazwa, statystyki
wywolan z pamieci), uzycie czatu, liczby wierszy, indeks RAG, baza i dysk.

Kazdy element liczony osobno - brak indeksu, uszkodzona baza Chromy albo
blad zapytania daja null i opis bledu w tej sekcji, a nie 500 dla calosci.
Nigdy nie zwraca sekretow (kluczy API, DATABASE_URL z haslem) ani sciezek
plikow. Wynik jest trzymany ~15 s (DiagnosticsCache), refresh=1 go pomija.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Generic, TypeVar

from sqlalchemy import Select, distinct, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session

from .. import database
from ..llm import stats as llm_stats
from ..llm.generate import current_model
from ..llm.provider import current_provider
from ..llm.stats import describe_error
from ..models import Conversation, DailyUsage, Message, MessageFeedback, SecurityIncident, User
from ..rag import context_builder
from ..rag.lexical import DEFAULT_DB_PATH as DEFAULT_LEXICAL_DB
from ..rag.lexical import TABLE as LEXICAL_TABLE
from ..rag.vectorstore import COLLECTION_NAME, DEFAULT_PERSIST_DIR
from .schemas import (
    DiagnosticsResponse,
    LlmDiagnostics,
    RagDiagnostics,
    StorageDiagnostics,
    TotalsDiagnostics,
    UsageDiagnostics,
)

logger = logging.getLogger(__name__)

# Plik bazy Chromy w katalogu vectorstore - bez niego nie otwieramy klienta
# (PersistentClient zalozylby pusta baze).
CHROMA_DB_FILE = "chroma.sqlite3"
# Przy liczeniu daty ingestu nie przegladamy dowolnie wielu plikow.
MAX_SCANNED_FILES = 10_000
_SQLITE_SIDE_FILES = ("-wal", "-shm", "-journal")
STATS_WINDOW_DAYS = 7

# Jak dlugo trzymamy policzona diagnostyke (liczenie otwiera Chrome i skanuje dataset/).
CACHE_TTL_SECONDS = 15.0
# Sciezki w komunikatach bledow (np. z sqlite3, Chromy): C:\..., /app/..., dataset/...
_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|/|\.{1,2}[\\/]|\b[\w.-]+[\\/])[^\s'\"]*")
_PATH_PLACEHOLDER = "<sciezka>"

T = TypeVar("T")
# typ wartosci w DiagnosticsCache
V = TypeVar("V")


@dataclass(frozen=True)
class DiagnosticsConfig:
    dataset_dir: Path
    vectorstore_dir: Path
    lexical_db: Path
    database_url: str


def get_diagnostics_config() -> DiagnosticsConfig:
    """Dependency FastAPI: sciezki indeksow i bazy (testy podmieniaja na tmp)."""
    return DiagnosticsConfig(
        dataset_dir=Path(DEFAULT_PERSIST_DIR).parent,
        vectorstore_dir=Path(DEFAULT_PERSIST_DIR),
        lexical_db=Path(DEFAULT_LEXICAL_DB),
        database_url=database.DATABASE_URL,
    )


def _public_error(error: BaseException) -> str:
    """Opis bledu dla panelu: bez sekretow (describe_error) i bez sciezek plikow."""
    return _PATH_PATTERN.sub(_PATH_PLACEHOLDER, describe_error(error))


def _attempt(fn: Callable[[], T]) -> tuple[T | None, str | None]:
    """Wynik albo (None, opis bledu) - bez przerywania calej diagnostyki.
    Pelny blad (ze sciezkami) trafia tylko do logu serwera."""
    try:
        return fn(), None
    except Exception as exc:
        logger.warning("diagnostics check failed: %s", describe_error(exc))
        return None, _public_error(exc)


# --- model -----------------------------------------------------------------------------------

def llm_section() -> LlmDiagnostics:
    snapshot = llm_stats.current_stats().snapshot()
    return LlmDiagnostics(
        provider=current_provider(),
        model=current_model(),
        started_at=snapshot.started_at,
        uptime_seconds=snapshot.uptime_seconds,
        total_calls=snapshot.total_calls,
        total_errors=snapshot.total_errors,
        recent_calls=snapshot.recent_calls,
        recent_errors=snapshot.recent_errors,
        avg_latency_ms=snapshot.avg_latency_ms,
        p95_latency_ms=snapshot.p95_latency_ms,
        last_error=snapshot.last_error,
        last_error_at=snapshot.last_error_at,
    )


# --- baza aplikacji ----------------------------------------------------------------------------

def _count(db: Session, stmt: Select[tuple[int]]) -> int:
    return int(db.execute(stmt).scalar_one() or 0)


def usage_section(db: Session, today: date) -> UsageDiagnostics:
    week_start = today - timedelta(days=STATS_WINDOW_DAYS - 1)

    def compute() -> UsageDiagnostics:
        active = DailyUsage.count > 0
        return UsageDiagnostics(
            questions_today=_count(db, select(func.coalesce(func.sum(DailyUsage.count), 0)).where(DailyUsage.day == today)),
            questions_7d=_count(db, select(func.coalesce(func.sum(DailyUsage.count), 0)).where(DailyUsage.day >= week_start)),
            active_users_today=_count(db, select(func.count(distinct(DailyUsage.user_id))).where(DailyUsage.day == today, active)),
            active_users_7d=_count(db, select(func.count(distinct(DailyUsage.user_id))).where(DailyUsage.day >= week_start, active)),
            error=None,
        )

    result, error = _attempt(compute)
    if result is not None:
        return result
    db.rollback()
    return UsageDiagnostics(questions_today=None, questions_7d=None, active_users_today=None, active_users_7d=None, error=error)


def totals_section(db: Session) -> TotalsDiagnostics:
    def compute() -> TotalsDiagnostics:
        return TotalsDiagnostics(
            users=_count(db, select(func.count()).select_from(User)),
            conversations=_count(db, select(func.count()).select_from(Conversation)),
            messages=_count(db, select(func.count()).select_from(Message)),
            open_reports=_count(db, select(func.count()).select_from(MessageFeedback).where(MessageFeedback.report_status == "open")),
            open_incidents=_count(db, select(func.count()).select_from(SecurityIncident).where(SecurityIncident.status == "open")),
            error=None,
        )

    result, error = _attempt(compute)
    if result is not None:
        return result
    db.rollback()
    return TotalsDiagnostics(users=None, conversations=None, messages=None, open_reports=None, open_incidents=None, error=error)


# --- indeks RAG ----------------------------------------------------------------------------------

def _vector_count(directory: Path) -> int:
    """Liczba wpisow w kolekcji Chromy. Uzywa juz zaladowanego retrievera,
    a bez niego otwiera klienta tylko na istniejacej bazie."""
    retriever = context_builder._default_retriever
    if retriever is not None and Path(retriever.vectorstore.persist_dir).resolve() == directory.resolve():
        return retriever.vectorstore.count()
    if not (directory / CHROMA_DB_FILE).is_file():
        raise FileNotFoundError("brak indeksu wektorowego")
    import chromadb

    client = chromadb.PersistentClient(path=os.fspath(directory))
    return int(client.get_collection(COLLECTION_NAME).count())


def _lexical_count(path: Path) -> int:
    """Liczba fragmentow w indeksie BM25; tylko odczyt (bez zakladania pliku)."""
    if not path.is_file():
        raise FileNotFoundError("brak indeksu leksykalnego")
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return int(con.execute(f"SELECT count(*) FROM {LEXICAL_TABLE}").fetchone()[0])
    finally:
        con.close()


def _written_by_ingest(name: str) -> bool:
    """Plik zmieniany tylko przez ingest. Chroma zapisuje swoja baze SQLite
    przy kazdym otwarciu (takze przez backend), a dzienniki SQLite i daty
    katalogow zmieniaja sie przy zwyklym odczycie - te pomijamy."""
    return not name.startswith(CHROMA_DB_FILE) and not name.endswith(_SQLITE_SIDE_FILES)


def _last_modified(directory: Path) -> datetime:
    """Najnowsza modyfikacja pliku ingestu w dataset/ (indeks leksykalny,
    segmenty wektorowe) - przyblizenie daty ostatniego ingestu."""
    if not directory.is_dir():
        raise FileNotFoundError("brak katalogu z danymi RAG")
    newest: float | None = None
    scanned = 0
    for root, _dirs, files in os.walk(directory):
        for name in filter(_written_by_ingest, files):
            mtime = os.stat(os.path.join(root, name)).st_mtime
            newest = mtime if newest is None else max(newest, mtime)
            scanned += 1
            if scanned >= MAX_SCANNED_FILES:
                break
        if scanned >= MAX_SCANNED_FILES:
            break
    if newest is None:
        raise FileNotFoundError("brak plikow indeksu")
    return datetime.fromtimestamp(newest, timezone.utc)


def rag_section(config: DiagnosticsConfig) -> RagDiagnostics:
    vector_count, vector_error = _attempt(lambda: _vector_count(config.vectorstore_dir))
    lexical_count, lexical_error = _attempt(lambda: _lexical_count(config.lexical_db))
    lexical_size = config.lexical_db.stat().st_size if lexical_error is None else None
    last_ingest, ingest_error = _attempt(lambda: _last_modified(config.dataset_dir))
    return RagDiagnostics(
        vector_count=vector_count,
        vector_error=vector_error,
        lexical_count=lexical_count,
        lexical_size_bytes=lexical_size,
        lexical_error=lexical_error,
        last_ingest_at=last_ingest,
        last_ingest_error=ingest_error,
    )


# --- baza i dysk -----------------------------------------------------------------------------------

def _sqlite_path(database_url: str) -> Path:
    """Sciezka pliku bazy SQLite z DATABASE_URL (bez ujawniania URL-a)."""
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise ValueError("nieprawidlowy DATABASE_URL") from None
    if url.get_backend_name() != "sqlite":
        raise ValueError(f"baza {url.get_backend_name()} - rozmiar pliku tylko dla SQLite")
    if not url.database or url.database == ":memory:":
        raise ValueError("baza SQLite w pamieci")
    return Path(url.database)


def _database_size(path: Path) -> int:
    """Rozmiar pliku bazy razem z dziennikiem WAL (jesli jest)."""
    size = path.stat().st_size
    wal = path.with_name(path.name + "-wal")
    return size + (wal.stat().st_size if wal.is_file() else 0)


def storage_section(config: DiagnosticsConfig) -> StorageDiagnostics:
    db_path, path_error = _attempt(lambda: _sqlite_path(config.database_url))
    if db_path is not None:
        size, size_error = _attempt(lambda: _database_size(db_path))
        volume = db_path.resolve().parent
    else:
        size, size_error = None, path_error
        volume = Path.cwd()
    usage, disk_error = _attempt(lambda: shutil.disk_usage(volume))
    return StorageDiagnostics(
        database_size_bytes=size,
        database_error=size_error,
        disk_free_bytes=usage.free if usage is not None else None,
        disk_total_bytes=usage.total if usage is not None else None,
        disk_error=disk_error,
    )


def collect_diagnostics(db: Session, config: DiagnosticsConfig, now: datetime, today: date) -> DiagnosticsResponse:
    """Wszystkie sekcje diagnostyki; zadna nie przerywa pozostalych."""
    return DiagnosticsResponse(
        generated_at=now,
        llm=llm_section(),
        usage=usage_section(db, today),
        totals=totals_section(db),
        rag=rag_section(config),
        storage=storage_section(config),
    )


class DiagnosticsCache(Generic[V]):
    """Ostatnia policzona diagnostyka na `ttl_seconds`. Blokada sprawia, ze
    rownolegle zapytania adminow licza ja raz (pozostale czekaja na wynik)."""

    def __init__(self, ttl_seconds: float = CACHE_TTL_SECONDS, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._value: V | None = None
        self._expires_at = 0.0

    def get(self, compute: Callable[[], V], refresh: bool) -> V:
        """Wartosc z cache albo nowo policzona (refresh=True zawsze liczy)."""
        with self._lock:
            now = self._monotonic()
            if refresh or self._value is None or now >= self._expires_at:
                self._value = compute()
                self._expires_at = now + self._ttl
            return self._value


_CACHE: DiagnosticsCache[DiagnosticsResponse] = DiagnosticsCache()


def get_diagnostics_cache() -> DiagnosticsCache[DiagnosticsResponse]:
    """Dependency FastAPI: wspolny cache diagnostyki (testy podmieniaja)."""
    return _CACHE
