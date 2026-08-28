"""
Retriever: laczy Encoder + VectorStore i zwraca top-k pasujacych fragmentow
dla danego zapytania. To warstwa posrednia miedzy vectorstore.py a
context_builder.py (publicznym interfejsem dla src/backend/llm/).
"""

from .encoder import Encoder
from .lexical import LexicalIndex, tokenize
from .staff import DEFAULT_LIMIT as DEFAULT_STAFF_LIMIT
from .staff import StaffIndex
from .vectorstore import VectorStore

OTHER_SOURCES = ("strony", "usos")
MORDOR_SOURCES = ("mordor",)
POOL_FACTOR = 3


class Retriever:
    def __init__(
        self,
        encoder: Encoder | None = None,
        vectorstore: VectorStore | None = None,
        staff: StaffIndex | None = None,
        lexical: LexicalIndex | None = None,
    ):
        self.encoder = encoder or Encoder()
        self.vectorstore = vectorstore or VectorStore(encoder=self.encoder)
        self._lexical = lexical
        self._lexical_loaded = lexical is not None
        self._staff = staff
        self._staff_loaded = staff is not None

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Zwraca liste top-k trafien: dict z kluczami id/value/content_type/
        source/metadata/distance (patrz VectorStore.search)."""
        return self.vectorstore.search(query, top_k=top_k)

    def _get_lexical(self) -> LexicalIndex | None:
        if not self._lexical_loaded:
            self._lexical_loaded = True
            index = LexicalIndex()
            if index.count():
                self._lexical = index
        return self._lexical

    def _get_staff(self) -> StaffIndex | None:
        if not self._staff_loaded:
            self._staff_loaded = True
            index = self._get_lexical()
            if index is not None and index.count("usos"):
                self._staff = StaffIndex.from_collection(self.vectorstore.collection, index)
        return self._staff

    def _lexical_hits(self, tokens: list[str], sources: tuple[str, ...], limit: int) -> list[dict]:
        index = self._get_lexical()
        if index is None or limit <= 0:
            return []
        return self.vectorstore.get_by_ids(
            index.search(index.selective_tokens(tokens), sources, limit=limit)
        )

    @staticmethod
    def _interleave(vector_hits: list[dict], lexical_hits: list[dict], k: int) -> list[dict]:
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
        staff = self._get_staff()
        if staff is None or limit <= 0:
            return []
        return self.vectorstore.get_by_ids(staff.lookup(query, limit=limit))
