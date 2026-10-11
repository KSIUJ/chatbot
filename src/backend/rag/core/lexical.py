"""Indeks leksykalny BM25 (SQLite FTS5, lexical.db indeksu) dzialajacy obok vectorstore.

Bez jawnej sciezki czyta biezacy indeks (core/index_store.py: dataset/CURRENT
albo stary dataset/lexical.db) i przechodzi na nowy, gdy wskaznik sie zmieni.
"""

import logging
import os
import re
import sqlite3
import threading

from .documents import Document
from .index_store import IndexLocation, LocationWatch, legacy_location

logger = logging.getLogger(__name__)

# stary uklad (bez dataset/CURRENT); biezacy indeks wskazuje index_store
DEFAULT_DB_PATH = os.fspath(legacy_location().lexical)
TABLE = "chunks_fts"
TITLE_WEIGHT = 5.0
TITLE_MAX_CHARS = 200
MAX_DOC_FREQ_RATIO = 0.02
# limit parametrow jednego zapytania SQLite
_ID_BATCH = 500

_FOLD = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold(text: str) -> str:
    return text.translate(_FOLD)


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", fold(text).lower(), re.UNICODE)


class LexicalIndex:
    def __init__(self, db_path: str | None = None):
        # bez sciezki: biezacy indeks wg dataset/CURRENT, sledzony w trakcie pracy
        self._watch = LocationWatch() if db_path is None else None
        self._lock = threading.Lock()
        self._location: IndexLocation | None = None
        self._open(self._watch.current() if self._watch else None, db_path)

    def _open(self, location: IndexLocation | None, db_path: str | None = None) -> None:
        path = os.fspath(location.lexical) if location is not None else db_path
        assert path is not None
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        con = sqlite3.connect(path, check_same_thread=False)
        con.execute(
            f"""CREATE VIRTUAL TABLE IF NOT EXISTS {TABLE} USING fts5(
                doc_id UNINDEXED,
                source UNINDEXED,
                title,
                text,
                tokenize="unicode61 remove_diacritics 2"
            )"""
        )
        con.commit()
        # poprzednie polaczenie zamyka GC - inny watek moze jeszcze z niego czytac
        self._doc_freq: dict[str, int] = {}
        self._total: int | None = None
        self._con = con
        self._location = location
        self.db_path = path

    def _refresh(self) -> sqlite3.Connection:
        """Polaczenie z biezacym indeksem (zmiana dataset/CURRENT = nowy plik)."""
        if self._watch is not None:
            location = self._watch.current()
            if location != self._location:
                with self._lock:
                    if location != self._location:
                        logger.info("rag index: przelaczam indeks BM25 na %s", location.name or "stary uklad")
                        self._open(location)
        return self._con

    def add_documents(self, documents: list[Document]) -> None:
        self.add_raw([(d.id, d.source, d.embed_text) for d in documents])

    def add_raw(self, rows: list[tuple[str, str, str]]) -> None:
        if not rows:
            return

        con = self._con
        ids = [r[0] for r in rows]
        for i in range(0, len(ids), _ID_BATCH):
            chunk = ids[i : i + _ID_BATCH]
            con.execute(f"DELETE FROM {TABLE} WHERE doc_id IN ({','.join('?' * len(chunk))})", chunk)
        con.executemany(
            f"INSERT INTO {TABLE} (doc_id, source, title, text) VALUES (?, ?, ?, ?)",
            [
                (doc_id, source, fold(text.split("\n", 1)[0][:TITLE_MAX_CHARS]), fold(text))
                for doc_id, source, text in rows
            ],
        )
        con.commit()
        self._doc_freq.clear()
        self._total = None

    def delete_ids(self, ids: list[str]) -> None:
        con = self._con
        for i in range(0, len(ids), _ID_BATCH):
            chunk = ids[i : i + _ID_BATCH]
            con.execute(f"DELETE FROM {TABLE} WHERE doc_id IN ({','.join('?' * len(chunk))})", chunk)
        con.commit()
        self._doc_freq.clear()
        self._total = None

    def source_ids(self, source: str) -> set[str]:
        rows = self._refresh().execute(f"SELECT doc_id FROM {TABLE} WHERE source = ?", (source,))
        return {row[0] for row in rows}

    def document_frequency(self, token: str) -> int:
        con = self._refresh()
        if token not in self._doc_freq:
            self._doc_freq[token] = con.execute(
                f"SELECT count(*) FROM {TABLE} WHERE {TABLE} MATCH ?", (f'"{token}"',)
            ).fetchone()[0]
        return self._doc_freq[token]

    def selective_tokens(self, tokens: list[str]) -> list[str]:
        self._refresh()
        if self._total is None:
            self._total = self.count()
        if not self._total:
            return tokens

        ceiling = MAX_DOC_FREQ_RATIO * self._total
        selective = [t for t in tokens if self.document_frequency(t) <= ceiling]
        return selective or tokens

    def search(self, tokens: list[str], sources: tuple[str, ...], limit: int = 5) -> list[str]:
        if not tokens or not sources or limit <= 0:
            return []

        match = " OR ".join(f'"{t}"' for t in tokens)
        placeholders = ",".join("?" * len(sources))
        rows = self._refresh().execute(
            f"""SELECT doc_id FROM {TABLE}
                WHERE {TABLE} MATCH ? AND source IN ({placeholders})
                ORDER BY bm25({TABLE}, {TITLE_WEIGHT}, 1.0), doc_id
                LIMIT ?""",
            (match, *sources, limit),
        ).fetchall()
        return [row[0] for row in rows]

    def delete_source(self, source: str) -> int:
        cur = self._con.execute(f"DELETE FROM {TABLE} WHERE source = ?", (source,))
        self._con.commit()
        self._doc_freq.clear()
        self._total = None
        return cur.rowcount

    def source_counts(self) -> dict[str, int]:
        rows = self._refresh().execute(f"SELECT source, count(*) FROM {TABLE} GROUP BY source")
        return {source: count for source, count in rows}

    def count(self, source: str | None = None) -> int:
        con = self._refresh()
        if source is None:
            return con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        return con.execute(f"SELECT count(*) FROM {TABLE} WHERE source = ?", (source,)).fetchone()[0]

    def close(self) -> None:
        self._con.close()
