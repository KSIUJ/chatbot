"""
Retriever: hybrydowe wyszukiwanie (wektory z VectorStore + BM25 z LexicalIndex)
oraz wyszukiwarka pracownikow (StaffIndex). Uzywany przez context_builder.py.
"""

import threading
import time

from .encoder import Encoder
from .lexical import LexicalIndex, tokenize
from .staff import DEFAULT_LIMIT as DEFAULT_STAFF_LIMIT
from .staff import StaffIndex
from .vectorstore import VectorStore

OTHER_SOURCES = ("strony", "usos")
MORDOR_SOURCES = ("mordor",)
POOL_FACTOR = 3
# Co ile sekund ponawiac ladowanie indeksu leksykalnego/pracownikow, gdy byl pusty.
RELOAD_INTERVAL = 30.0


class Retriever:
    def __init__(
        self,
        encoder: Encoder | None = None,
        vectorstore: VectorStore | None = None,
        staff: StaffIndex | None = None,
        lexical: LexicalIndex | None = None,
        reload_interval: float = RELOAD_INTERVAL,
    ):
        self.encoder = encoder or Encoder()
        self.vectorstore = vectorstore or VectorStore(encoder=self.encoder)
        self._lexical = lexical
        self._staff = staff
        self._lexical_probe: LexicalIndex | None = None
        self._reload_interval = reload_interval
        self._next_load = 0.0
        self._load_lock = threading.Lock()

    def _load_indexes(self) -> None:
        """Laduje brakujace indeksy z dysku.

        Pusty indeks (np. ingest jeszcze nie przeszedl) nie jest zapamietywany:
        kolejna proba nastepuje najwczesniej po reload_interval sekundach.
        """
        if self._lexical is not None and self._staff is not None:
            return
        # /chat dziala w puli watkow - indeksy laduje jeden watek naraz
        with self._load_lock:
            now = time.monotonic()
            if now < self._next_load:
                return
            self._next_load = now + self._reload_interval

            if self._lexical is None:
                if self._lexical_probe is None:
                    self._lexical_probe = LexicalIndex()
                if self._lexical_probe.count():
                    self._lexical = self._lexical_probe

            if self._staff is None and self._lexical is not None and self._lexical.count("usos"):
                self._staff = StaffIndex.from_collection(self.vectorstore.collection, self._lexical)

    def _lexical_hits(self, tokens: list[str], sources: tuple[str, ...], limit: int) -> list[dict]:
        self._load_indexes()
        index = self._lexical
        if index is None or limit <= 0:
            return []
        return self.vectorstore.get_by_ids(
            index.search(index.selective_tokens(tokens), sources, limit=limit)
        )

    @staticmethod
    def _interleave(vector_hits: list[dict], lexical_hits: list[dict], k: int) -> list[dict]:
        """Laczy trafienia: polowa miejsc (zaokraglona w gore) dla BM25, reszta
        dla wektorow, bez duplikatow; nadmiarowe trafienia BM25 uzupelniaja koniec."""
        if k <= 0:
            return []

        from_lexical = k // 2 + k % 2
        merged: list[dict] = []
        seen: set[str] = set()

        for pool in (lexical_hits[:from_lexical], vector_hits, lexical_hits[from_lexical:]):
            for hit in pool:
                if len(merged) >= k:
                    return merged
                if hit["id"] not in seen:
                    seen.add(hit["id"])
                    merged.append(hit)
        return merged

    def retrieve_split(
        self, query: str, k_mordor: int = 5, k_other: int = 5
    ) -> dict[str, list[dict]]:
        """Top-k trafien osobno dla mordoru i dla zrodel oficjalnych (strony, usos)."""
        vectors = self.vectorstore.search_split(
            query, k_mordor=k_mordor * POOL_FACTOR, k_other=k_other * POOL_FACTOR
        )

        tokens = tokenize(query)
        return {
            "mordor": self._interleave(
                vectors["mordor"],
                self._lexical_hits(tokens, MORDOR_SOURCES, k_mordor * POOL_FACTOR),
                k_mordor,
            ),
            "other": self._interleave(
                vectors["other"],
                self._lexical_hits(tokens, OTHER_SOURCES, k_other * POOL_FACTOR),
                k_other,
            ),
        }

    def retrieve_staff(self, query: str, limit: int = DEFAULT_STAFF_LIMIT) -> list[dict]:
        """Wpisy USOS pracownikow wymienionych w zapytaniu (pusto, gdy brak nazwiska)."""
        self._load_indexes()
        if self._staff is None or limit <= 0:
            return []
        return self.vectorstore.get_by_ids(self._staff.lookup(query, limit=limit))
