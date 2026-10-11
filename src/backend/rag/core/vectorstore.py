"""
Baza wektorowa (ChromaDB, PersistentClient w katalogu vectorstore/ indeksu).

Jedna kolekcja dla wszystkich zrodel; zrodlo jest w metadanych kazdego wpisu
(`source`), a query zaweza wyniki do wybranych zrodel. Kazdy wpis ma tez
`content_hash` (document_hash) - po nim aktualizacja indeksu poznaje
zmienione dokumenty.

Wyszukiwanie jest dokladne: odleglosc do wszystkich wektorow wybranych zrodel
liczona w numpy (indeks ma kilka-kilkadziesiat tysiecy fragmentow). HNSW
Chromy jest przyblizony, a z filtrem po zrodle potrafil zgubic blizszego
sasiada zaleznie od wczesniejszych zapytan.

Bez jawnej sciezki VectorStore czyta biezacy indeks (core/index_store.py:
dataset/CURRENT albo stary dataset/vectorstore) i przechodzi na nowy, gdy
wskaznik sie zmieni.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from typing import TYPE_CHECKING

from .documents import Document
from .encoder import Encoder, encoder_settings
from .index_store import IndexLocation, LocationWatch, legacy_location, warn_on_mismatch

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

# stary uklad (bez dataset/CURRENT); biezacy indeks wskazuje index_store
DEFAULT_PERSIST_DIR = os.fspath(legacy_location().vectorstore)
COLLECTION_NAME = "chatbot_wmi"
HASH_KEY = "content_hash"
PAGE_SIZE = 1000


def document_hash(document: Document) -> str:
    """Skrot tresci dokumentu (tekst do wyszukiwania, tresc, typ, metadane)."""
    payload = json.dumps(
        [document.embed_text, document.value, document.content_type, document.metadata],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hit(id_: str, value: str, metadata: dict, distance: float | None) -> dict:
    return {
        "id": id_,
        "value": value,
        "content_type": metadata.get("content_type", "text"),
        "source": metadata.get("source"),
        "metadata": metadata,
        "distance": distance,
    }


class _Matrix:
    """Wszystkie wektory kolekcji w pamieci (wiersze posortowane po id)."""

    def __init__(self, ids: list[str], sources: list[str], embeddings: np.ndarray, count: int) -> None:
        import numpy as np

        self.ids = ids
        self.sources = np.array(sources, dtype=object)
        self.embeddings = embeddings
        self.norms = np.einsum("ij,ij->i", embeddings, embeddings)
        self.count = count


class VectorStore:
    def __init__(self, persist_dir: str | None = None, encoder: Encoder | None = None) -> None:
        self.encoder = encoder or Encoder()
        # bez sciezki: biezacy indeks wg dataset/CURRENT, sledzony w trakcie pracy
        self._watch = LocationWatch() if persist_dir is None else None
        self._lock = threading.Lock()
        self._retired = None
        self._location: IndexLocation | None = None
        self._open(self._watch.current() if self._watch else None, persist_dir)

    def _open(self, location: IndexLocation | None, persist_dir: str | None = None) -> None:
        import chromadb

        path = os.fspath(location.vectorstore) if location is not None else persist_dir
        assert path is not None
        os.makedirs(path, exist_ok=True)
        client = chromadb.PersistentClient(path=path)
        collection = client.get_or_create_collection(name=COLLECTION_NAME)
        # poprzedni klient zamykany dopiero przy kolejnej zmianie - inny watek
        # moze jeszcze konczyc na nim zapytanie
        if self._retired is not None:
            self._retired.close()
        self._retired = getattr(self, "_client", None)
        self._client = client
        self._collection = collection
        self._matrix: _Matrix | None = None
        self._location = location
        self.persist_dir = path
        self.index_name = location.name if location is not None else None
        self.mismatches = warn_on_mismatch(location, encoder_settings(self.encoder)) if location else []

    def _refresh(self) -> None:
        """Przejscie na nowy indeks, gdy dataset/CURRENT wskazuje inny katalog."""
        if self._watch is None:
            return
        location = self._watch.current()
        if location == self._location:
            return
        with self._lock:
            if location != self._location:
                logger.info("rag index: przelaczam vectorstore na %s", location.name or "stary uklad")
                self._open(location)

    @property
    def collection(self):
        self._refresh()
        return self._collection

    # --- zapis (CLI indeksu) -------------------------------------------------------------

    def add_documents(self, documents: list[Document]) -> None:
        """Embeduje i dodaje dokumenty do kolekcji (upsert po Document.id)."""
        if not documents:
            return

        embeddings = self.encoder.embed_batch([doc.embed_text for doc in documents])
        ids = [doc.id for doc in documents]
        values = [doc.value for doc in documents]
        metadatas = [
            {
                **doc.metadata,
                "source": doc.source,
                "content_type": doc.content_type,
                HASH_KEY: document_hash(doc),
            }
            for doc in documents
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=values,
            metadatas=metadatas,
        )
        self._matrix = None

    def filter_new(self, documents: list[Document]) -> list[Document]:
        """Dokumenty, ktorych id jeszcze nie ma w kolekcji."""
        if not documents:
            return []

        ids = [d.id for d in documents]
        present: set[str] = set()
        for i in range(0, len(ids), PAGE_SIZE):
            got = self._collection.get(ids=ids[i : i + PAGE_SIZE], include=[])
            present.update(got.get("ids", []))

        return [d for d in documents if d.id not in present]

    def source_hashes(self, source: str) -> dict[str, str | None]:
        """{id: content_hash} wpisow zrodla (None = wpis bez skrotu, np. ze starego ingestu)."""
        hashes: dict[str, str | None] = {}
        offset = 0
        while True:
            got = self._collection.get(
                where={"source": source}, include=["metadatas"], limit=PAGE_SIZE, offset=offset
            )
            if not got["ids"]:
                return hashes
            for id_, metadata in zip(got["ids"], got["metadatas"]):
                hashes[id_] = (metadata or {}).get(HASH_KEY)
            offset += len(got["ids"])

    def delete_ids(self, ids: list[str]) -> None:
        for i in range(0, len(ids), PAGE_SIZE):
            self._collection.delete(ids=ids[i : i + PAGE_SIZE])
        self._matrix = None

    def delete_source(self, source: str) -> int:
        """Usuwa wszystkie wpisy zrodla; zwraca liczbe usunietych."""
        before = self._collection.count()
        self._collection.delete(where={"source": source})
        self._matrix = None
        return before - self._collection.count()

    def close(self) -> None:
        for client in (self._retired, self._client):
            if client is not None:
                client.close()
        self._retired = None

    # --- odczyt --------------------------------------------------------------------------

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Wpisy o podanych id, w kolejnosci `ids` (brakujace sa pomijane)."""
        if not ids:
            return []

        got = self.collection.get(ids=ids, include=["documents", "metadatas"])
        by_id = {}
        for id_, value, metadata in zip(got["ids"], got["documents"], got["metadatas"]):
            by_id[id_] = _hit(id_, value, metadata, None)
        return [by_id[i] for i in ids if i in by_id]

    def _load_matrix(self) -> _Matrix:
        """Wektory calej kolekcji; ponownie, gdy liczba wpisow sie zmienila."""
        import numpy as np

        collection = self.collection
        count = collection.count()
        matrix = self._matrix
        if matrix is not None and matrix.count == count:
            return matrix

        rows: list[tuple[str, str, np.ndarray]] = []
        offset = 0
        while True:
            got = collection.get(include=["embeddings", "metadatas"], limit=PAGE_SIZE, offset=offset)
            if not len(got["ids"]):
                break
            for id_, embedding, metadata in zip(got["ids"], got["embeddings"], got["metadatas"]):
                rows.append((id_, (metadata or {}).get("source", ""), embedding))
            offset += len(got["ids"])
        rows.sort(key=lambda row: row[0])

        if rows:
            embeddings = np.asarray([row[2] for row in rows], dtype=np.float32)
        else:
            embeddings = np.zeros((0, 0), dtype=np.float32)
        matrix = _Matrix([row[0] for row in rows], [row[1] for row in rows], embeddings, count)
        self._matrix = matrix
        return matrix

    def query(self, embedding: list[float], top_k: int, sources: tuple[str, ...]) -> list[dict]:
        """Top-k wpisow ze wskazanych zrodel dla gotowego wektora zapytania.

        Dokladne: kwadrat odleglosci euklidesowej (jak "l2" Chromy) do kazdego
        wektora wybranych zrodel; remisy rozstrzyga id, wiec wynik zalezy
        tylko od zawartosci indeksu.
        """
        import numpy as np

        if top_k <= 0 or not sources:
            return []
        matrix = self._load_matrix()
        if not matrix.ids:
            return []

        rows = np.flatnonzero(np.isin(matrix.sources, list(sources)))
        if not rows.size:
            return []
        q = np.asarray(embedding, dtype=np.float32)
        distances = matrix.norms[rows] - 2.0 * (matrix.embeddings[rows] @ q) + float(q @ q)
        best = rows[np.argsort(distances, kind="stable")[:top_k]]
        by_row = dict(zip(rows.tolist(), distances.tolist()))

        hits = self.get_by_ids([matrix.ids[i] for i in best])
        distance_by_id = {matrix.ids[i]: max(0.0, by_row[i]) for i in best}
        for hit in hits:
            hit["distance"] = distance_by_id[hit["id"]]
        return hits

    def source_counts(self) -> dict[str, int]:
        """Liczba wpisow kazdego zrodla."""
        counts: dict[str, int] = {}
        offset = 0
        collection = self.collection
        while True:
            got = collection.get(include=["metadatas"], limit=PAGE_SIZE, offset=offset)
            if not got["ids"]:
                return counts
            for metadata in got["metadatas"]:
                source = (metadata or {}).get("source", "")
                counts[source] = counts.get(source, 0) + 1
            offset += len(got["ids"])

    def count(self) -> int:
        return self.collection.count()
