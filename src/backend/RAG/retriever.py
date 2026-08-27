"""
Retriever: laczy Encoder + VectorStore i zwraca top-k pasujacych fragmentow
dla danego zapytania. To warstwa posrednia miedzy vectorstore.py a
context_builder.py (publicznym interfejsem dla src/backend/llm/).
"""

from .encoder import Encoder
from .lexical import LexicalIndex
from .staff import DEFAULT_LIMIT as DEFAULT_STAFF_LIMIT
from .staff import StaffIndex
from .vectorstore import VectorStore


class Retriever:
    def __init__(
        self,
        encoder: Encoder | None = None,
        vectorstore: VectorStore | None = None,
        staff: StaffIndex | None = None,
    ):
        self.encoder = encoder or Encoder()
        self.vectorstore = vectorstore or VectorStore(encoder=self.encoder)
        self._staff = staff
        self._staff_loaded = staff is not None

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Zwraca liste top-k trafien: dict z kluczami id/value/content_type/
        source/metadata/distance (patrz VectorStore.search)."""
        return self.vectorstore.search(query, top_k=top_k)

    def retrieve_split(
        self, query: str, k_mordor: int = 5, k_other: int = 5
    ) -> dict[str, list[dict]]:
        return self.vectorstore.search_split(query, k_mordor=k_mordor, k_other=k_other)

    def _get_staff(self) -> StaffIndex | None:
        if not self._staff_loaded:
            self._staff_loaded = True
            index = LexicalIndex()
            if index.count("usos"):
                self._staff = StaffIndex.from_collection(self.vectorstore.collection, index)
        return self._staff

    def retrieve_staff(self, query: str, limit: int = DEFAULT_STAFF_LIMIT) -> list[dict]:
        staff = self._get_staff()
        if staff is None or limit <= 0:
            return []
        return self.vectorstore.get_by_ids(staff.lookup(query, limit=limit))
