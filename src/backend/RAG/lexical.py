import os
import re
import sqlite3

from .ingest.schema import Document

DEFAULT_DB_PATH = os.path.join("dataset", "lexical.db")
TABLE = "chunks_fts"
TITLE_WEIGHT = 5.0
TITLE_MAX_CHARS = 200

_FOLD = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold(text: str) -> str:
    return text.translate(_FOLD)


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", fold(text).lower(), re.UNICODE)


class LexicalIndex:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.execute(
            f"""CREATE VIRTUAL TABLE IF NOT EXISTS {TABLE} USING fts5(
                doc_id UNINDEXED,
                source UNINDEXED,
                title,
                text,
                tokenize="unicode61 remove_diacritics 2"
            )"""
        )
        self._con.commit()

    def add_documents(self, documents: list[Document]) -> None:
        if not documents:
            return

        ids = [d.id for d in documents]
        placeholders = ",".join("?" * len(ids))
        self._con.execute(f"DELETE FROM {TABLE} WHERE doc_id IN ({placeholders})", ids)
        self._con.executemany(
            f"INSERT INTO {TABLE} (doc_id, source, title, text) VALUES (?, ?, ?, ?)",
            [
                (
                    d.id,
                    d.source,
                    fold(d.embed_text.split("\n", 1)[0][:TITLE_MAX_CHARS]),
                    fold(d.embed_text),
                )
                for d in documents
            ],
        )
        self._con.commit()

    def add_raw(self, rows: list[tuple[str, str, str]]) -> None:
        if not rows:
            return

        ids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(ids))
        self._con.execute(f"DELETE FROM {TABLE} WHERE doc_id IN ({placeholders})", ids)
        self._con.executemany(
            f"INSERT INTO {TABLE} (doc_id, source, title, text) VALUES (?, ?, ?, ?)",
            [
                (doc_id, source, fold(text.split("\n", 1)[0][:TITLE_MAX_CHARS]), fold(text))
                for doc_id, source, text in rows
            ],
        )
        self._con.commit()

    def search(self, tokens: list[str], sources: tuple[str, ...], limit: int = 5) -> list[str]:
        if not tokens or not sources or limit <= 0:
            return []

        match = " OR ".join(f'"{t}"' for t in tokens)
        placeholders = ",".join("?" * len(sources))
        rows = self._con.execute(
            f"""SELECT doc_id FROM {TABLE}
                WHERE {TABLE} MATCH ? AND source IN ({placeholders})
                ORDER BY bm25({TABLE}, {TITLE_WEIGHT}, 1.0)
                LIMIT ?""",
            (match, *sources, limit),
        ).fetchall()
        return [row[0] for row in rows]

    def count(self, source: str | None = None) -> int:
        if source is None:
            return self._con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        return self._con.execute(
            f"SELECT count(*) FROM {TABLE} WHERE source = ?", (source,)
        ).fetchone()[0]
