"""
Retriever: dokladne wyszukiwania zrodel (np. pracownik po nazwisku) i
hybrydowe wyszukiwanie w pulach z rejestru. Kazda pula:

1. kandydaci z wektorow (VectorStore) i BM25 (LexicalIndex) polaczeni
   Reciprocal Rank Fusion,
2. prog trafnosci: odpadaja kandydaci wyraznie nietrafni (niskie podobienstwo
   do zapytania albo duzo nizsze niz najlepszego kandydata puli); z wlaczonym
   rerankerem (rerank.py, RAG_RERANKER_MODEL) zamiast tego reranker ustawia
   kandydatow od nowa i odrzuca slabo ocenionych (RAG_RERANKER_MIN_SCORE),
3. wybor: najwyzej per_document chunkow jednego dokumentu, sasiednie chunki
   sklejone w jeden fragment, dopoki starcza budzetu znakow puli.

Wynik to sekcje kontekstu w kolejnosci; uzywa go context.py.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Container, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from ..registry import POOLS, Pool, create_sources
from ..sources.base import RagSource
from .encoder import Encoder
from .lexical import LexicalIndex, tokenize
from .rerank import Reranker, default_reranker
from .vectorstore import VectorStore

# stala RRF: wynik kandydata = suma 1 / (RRF_K + pozycja) po obu listach
RRF_K = 60
# ilu najlepszych kandydatow po fuzji ocenia reranker
RERANK_TOP = 20
# najkrotsza zakladka sprawdzana przy sklejaniu sasiednich chunkow
MIN_OVERLAP = 20
# Co ile sekund ponawiac ladowanie indeksu leksykalnego i dokladnych
# wyszukiwan, gdy byly puste.
RELOAD_INTERVAL = 30.0


@dataclass(frozen=True)
class Section:
    header: str
    hits: list[dict]


@dataclass(frozen=True)
class Relevance:
    """Prog trafnosci kandydatow puli na podstawie podobienstwa cosinusowego
    do zapytania (wektory znormalizowane, wiec iloczyn skalarny).

    Podobienstwa modelu embeddingow sa scisniete (pytania spoza danych maja
    najlepsze trafienie ~0.78-0.88, trafne zrodla ~0.79-0.95), wiec sam prog
    bezwzgledny niewiele odsiewa; drugi warunek to odstep od najlepszego
    kandydata puli - trafne zrodlo prawie zawsze lezy blisko niego.
    """

    # minimalne podobienstwo kandydata
    min_similarity: float
    # najwiekszy dopuszczalny odstep od najlepszego kandydata puli
    max_gap: float

    def filter(self, candidates: list[Candidate]) -> list[Candidate]:
        similarities = [c.similarity for c in candidates if c.similarity is not None]
        if not similarities:
            return candidates
        floor = max(self.min_similarity, max(similarities) - self.max_gap)
        return [c for c in candidates if c.similarity is None or c.similarity >= floor]


# Skalibrowane na rag_eval dla sdadas/mmlw-roberta-large (inny model embeddingow
# = ponowna kalibracja).
DEFAULT_RELEVANCE = Relevance(min_similarity=0.78, max_gap=0.03)
NO_THRESHOLD = Relevance(min_similarity=float("-inf"), max_gap=float("inf"))


@dataclass
class Candidate:
    hit: dict
    score: float = 0.0
    vector_rank: int | None = None
    lexical_rank: int | None = None
    similarity: float | None = None


def fuse(vector_hits: list[dict], lexical_hits: list[dict], rrf_k: int = RRF_K) -> list[Candidate]:
    """Reciprocal Rank Fusion obu list; kandydaci od najwyzszego wyniku
    (remis: kolejnosc z listy wektorowej)."""
    by_id: dict[str, Candidate] = {}
    for ranked, attr in ((vector_hits, "vector_rank"), (lexical_hits, "lexical_rank")):
        for rank, hit in enumerate(ranked, start=1):
            candidate = by_id.setdefault(hit["id"], Candidate(hit))
            if getattr(candidate, attr) is None:
                setattr(candidate, attr, rank)
                candidate.score += 1.0 / (rrf_k + rank)
    return sorted(by_id.values(), key=lambda c: c.score, reverse=True)


def document_key(hit: dict) -> str:
    """Dokument, z ktorego pochodzi chunk: notatka KSI, strona (url), plik
    Mordoru (katalog + plik); inaczej sam wpis (np. karta pracownika)."""
    metadata = hit.get("metadata") or {}
    source = hit.get("source") or ""
    if metadata.get("note"):
        return f"{source}|note|{metadata['note']}"
    if metadata.get("url"):
        return f"{source}|{metadata['url']}"
    if metadata.get("source_file"):
        return f"{source}|{metadata.get('directory') or ''}/{metadata['source_file']}"
    return hit["id"]


def join_chunks(first: str, second: str) -> str:
    """Skleja kolejne chunki dokumentu, bez powtorzonej zakladki."""
    for size in range(min(len(first), len(second)), MIN_OVERLAP - 1, -1):
        if first.endswith(second[:size]):
            return first + second[size:]
    return f"{first}\n{second}"


def _chunk_index(hit: dict) -> int | None:
    index = (hit.get("metadata") or {}).get("chunk_index")
    return index if isinstance(index, int) else None


def _text_length(hit: dict) -> int:
    return len(hit.get("value") or "") if hit.get("content_type", "text") == "text" else 0


@dataclass
class _Fragment:
    """Fragment kontekstu: jeden chunk albo kilka sasiednich chunkow dokumentu."""

    key: str
    # chunki fragmentu; pierwszy to najlepiej oceniony (jego metadane zostaja)
    hits: list[dict] = field(default_factory=list)

    def adjacent_to(self, hit: dict) -> bool:
        index = _chunk_index(hit)
        indexes = [_chunk_index(h) for h in self.hits]
        if index is None or None in indexes:
            return False
        return index in (min(indexes) - 1, max(indexes) + 1)

    def value(self, extra: dict | None = None) -> str:
        hits = sorted([*self.hits, *([extra] if extra else [])], key=lambda h: _chunk_index(h) or 0)
        value = hits[0]["value"]
        for hit in hits[1:]:
            value = join_chunks(value, hit["value"])
        return value

    def to_hit(self) -> dict:
        if len(self.hits) == 1:
            return self.hits[0]
        return {**self.hits[0], "value": self.value(), "merged_ids": [h["id"] for h in self.hits]}


def select(candidates: Iterable[dict], pool: Pool) -> list[dict]:
    """Trafienia puli z kandydatow (od najlepszego): najwyzej per_document
    chunkow dokumentu, sasiednie chunki sklejone w jeden fragment, najwyzej k
    fragmentow; nowy fragment wchodzi, dopoki miesci sie w budzecie (pierwsze
    min_hits zawsze)."""
    fragments: list[_Fragment] = []
    per_document: Counter[str] = Counter()
    used = 0
    for hit in candidates:
        key = document_key(hit)
        if per_document[key] >= pool.per_document:
            continue
        fragment = next((f for f in fragments if f.key == key and f.adjacent_to(hit)), None)
        if fragment is not None:
            grown = len(fragment.value(hit)) - len(fragment.value())
            if used + grown <= pool.budget:
                fragment.hits.append(hit)
                per_document[key] += 1
                used += grown
            continue
        if len(fragments) >= pool.k:
            continue
        size = _text_length(hit)
        if len(fragments) >= pool.min_hits and used + size > pool.budget:
            break
        fragments.append(_Fragment(key, [hit]))
        per_document[key] += 1
        used += size
    return [f.to_hit() for f in fragments]


def hit_ids(hit: dict) -> list[str]:
    """Id wpisow skladajacych sie na trafienie (sklejony fragment ma kilka)."""
    return hit.get("merged_ids") or [hit["id"]]


class Retriever:
    def __init__(
        self,
        encoder: Encoder | None = None,
        vectorstore: VectorStore | None = None,
        lexical: LexicalIndex | None = None,
        sources: Mapping[str, RagSource] | None = None,
        pools: Sequence[Pool] = POOLS,
        reload_interval: float = RELOAD_INTERVAL,
        relevance: Relevance = DEFAULT_RELEVANCE,
        reranker: Reranker | None = None,
        rrf_k: int = RRF_K,
    ):
        self.encoder = encoder or Encoder()
        self.vectorstore = vectorstore or VectorStore(encoder=self.encoder)
        self.sources = dict(sources) if sources is not None else create_sources()
        self.pools = tuple(pools)
        self.relevance = relevance
        self.reranker = reranker if reranker is not None else default_reranker()
        self.rrf_k = rrf_k
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

    def _set_similarities(self, candidates: list[Candidate], embedding: list[float]) -> None:
        """Podobienstwo kazdego kandydata do zapytania z wektorow w kolekcji
        (takze trafien samego BM25, ktorych nie ma na liscie wektorowej)."""
        if not candidates:
            return
        got = self.vectorstore.collection.get(ids=[c.hit["id"] for c in candidates], include=["embeddings"])
        vectors = dict(zip(got["ids"], got["embeddings"]))
        query = np.asarray(embedding, dtype=float)
        for candidate in candidates:
            vector = vectors.get(candidate.hit["id"])
            if vector is not None:
                candidate.similarity = float(np.dot(query, np.asarray(vector, dtype=float)))

    def _rerank(self, query: str, candidates: list[Candidate]) -> list[Candidate]:
        if self.reranker is None or not candidates:
            return candidates
        top = candidates[:RERANK_TOP]
        texts = [c.hit.get("value") or "" for c in top]
        scores = self.reranker.scores(query, texts)
        min_score = getattr(self.reranker, "min_score", None)
        ranked = sorted(zip(scores, top), key=lambda pair: pair[0], reverse=True)
        return [c for score, c in ranked if min_score is None or score >= min_score]

    def candidates(
        self, pool: Pool, query: str, embedding: list[float], tokens: list[str], exclude: Container[str] = frozenset()
    ) -> list[Candidate]:
        """Kandydaci puli po fuzji, progu trafnosci i ewentualnym rerankingu
        (bez wpisow z `exclude`, np. juz pokazanych w sekcji PRACOWNIK)."""
        fused = fuse(
            self.vectorstore.query(embedding, pool.candidates, pool.sources),
            self._lexical_hits(tokens, pool.sources, pool.candidates),
            self.rrf_k,
        )
        fused = [c for c in fused if c.hit["id"] not in exclude]
        if self.reranker is not None:
            # ocena rerankera jest lepszym progiem niz podobienstwo embeddingow
            return self._rerank(query, fused)
        self._set_similarities(fused, embedding)
        return self.relevance.filter(fused)

    def lookup_hits(self, source: RagSource, query: str) -> list[dict]:
        """Trafienia dokladnego wyszukiwania zrodla (pusto, gdy nie jest gotowe)."""
        self._load_indexes()
        if source.name not in self._lookups_ready:
            return []
        return self.vectorstore.get_by_ids(source.lookup(query, source.lookup_limit))

    def pool_hits(
        self, pool: Pool, query: str, embedding: list[float], tokens: list[str], exclude: Container[str] = frozenset()
    ) -> list[dict]:
        """Trafienia puli do kontekstu (select na kandydatach)."""
        return select((c.hit for c in self.candidates(pool, query, embedding, tokens, exclude)), pool)

    def retrieve(self, query: str) -> list[Section]:
        """Sekcje kontekstu: dokladne wyszukiwania, potem pule. Wpis obecny
        we wczesniejszej sekcji nie powtarza sie w kolejnej."""
        seen: set[str] = set()
        sections = []
        for source in self._lookup_sources():
            hits = [h for h in self.lookup_hits(source, query) if h["id"] not in seen]
            seen.update(h["id"] for h in hits)
            sections.append(Section(source.lookup_header or "", hits))

        embedding = self.encoder.embed_query(query)
        tokens = tokenize(query)
        for pool in self.pools:
            hits = self.pool_hits(pool, query, embedding, tokens, seen)
            seen.update(i for h in hits for i in hit_ids(h))
            sections.append(Section(pool.header, hits))
        return sections
