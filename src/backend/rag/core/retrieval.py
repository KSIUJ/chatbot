"""
Retriever: dokladne wyszukiwania zrodel (np. pracownik po nazwisku) i
hybrydowe wyszukiwanie w pulach z rejestru (wektory z VectorStore + BM25
z LexicalIndex). Wynik to sekcje kontekstu w kolejnosci; uzywa go context.py.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..registry import POOLS, Pool, create_sources
from ..sources.base import RagSource
from .encoder import Encoder
from .lexical import LexicalIndex, tokenize
from .vectorstore import VectorStore

POOL_FACTOR = 3
# Co ile sekund ponawiac ladowanie indeksu leksykalnego i dokladnych
# wyszukiwan, gdy byly puste.
RELOAD_INTERVAL = 30.0


@dataclass(frozen=True)
class Section:
    header: str
    hits: list[dict]


class Retriever:
    def __init__(
        self,
        encoder: Encoder | None = None,
        vectorstore: VectorStore | None = None,
        lexical: LexicalIndex | None = None,
        sources: Mapping[str, RagSource] | None = None,
        pools: Sequence[Pool] = POOLS,
        reload_interval: float = RELOAD_INTERVAL,
    ):
        self.encoder = encoder or Encoder()
        self.vectorstore = vectorstore or VectorStore(encoder=self.encoder)
        self.sources = dict(sources) if sources is not None else create_sources()
        self.pools = tuple(pools)
        self._lexical = lexical
        self._lexical_probe: LexicalIndex | None = None
        self._lookups_ready: set[str] = set()
        self._reload_interval = reload_interval
        self._next_load = 0.0
        self._load_lock = threading.Lock()

    def _lookup_sources(self) -> list[RagSource]:
        return [s for s in self.sources.values() if s.lookup_header]

    def _load_indexes(self) -> None:
        """Laduje indeks leksykalny z dysku i przygotowuje dokladne wyszukiwania.

        Pusty indeks (np. ingest jeszcze nie przeszedl) nie jest zapamietywany:
        kolejna proba nastepuje najwczesniej po reload_interval sekundach.
        """
        pending = [s for s in self._lookup_sources() if s.name not in self._lookups_ready]
        if self._lexical is not None and not pending:
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

            if self._lexical is not None:
                for source in pending:
                    if source.prepare_lookup(self.vectorstore, self._lexical):
                        self._lookups_ready.add(source.name)

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

    def lookup_hits(self, source: RagSource, query: str) -> list[dict]:
        """Trafienia dokladnego wyszukiwania zrodla (pusto, gdy nie jest gotowe)."""
        self._load_indexes()
        if source.name not in self._lookups_ready:
            return []
        return self.vectorstore.get_by_ids(source.lookup(query, source.lookup_limit))

    def pool_hits(self, pool: Pool, embedding: list[float], tokens: list[str]) -> list[dict]:
        """Top-k puli: wektory i BM25 z puli kandydatow k * POOL_FACTOR."""
        candidates = pool.k * POOL_FACTOR
        return self._interleave(
            self.vectorstore.query(embedding, candidates, pool.sources),
            self._lexical_hits(tokens, pool.sources, candidates),
            pool.k,
        )

    def retrieve(self, query: str) -> list[Section]:
        """Sekcje kontekstu: dokladne wyszukiwania, potem pule. Trafienie
        obecne we wczesniejszej sekcji nie powtarza sie w kolejnej."""
        sections = [Section(s.lookup_header or "", self.lookup_hits(s, query)) for s in self._lookup_sources()]
        embedding = self.encoder.embed_query(query)
        tokens = tokenize(query)
        sections += [Section(pool.header, self.pool_hits(pool, embedding, tokens)) for pool in self.pools]

        seen: set[str] = set()
        unique = []
        for section in sections:
            hits = [h for h in section.hits if h["id"] not in seen]
            seen.update(h["id"] for h in hits)
            unique.append(Section(section.header, hits))
        return unique
