"""
Retriever: laczy Encoder + VectorStore i zwraca top-k pasujacych fragmentow
dla danego zapytania. To warstwa posrednia miedzy vectorstore.py a
context_builder.py (publicznym interfejsem dla src/backend/llm/).
"""

from .encoder import Encoder
from .vectorstore import VectorStore


class Retriever:
    def __init__(self, encoder: Encoder | None = None, vectorstore: VectorStore | None = None):
        self.encoder = encoder or Encoder()
        self.vectorstore = vectorstore or VectorStore(encoder=self.encoder)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Zwraca liste top-k trafien: dict z kluczami id/value/content_type/
        source/metadata/distance (patrz VectorStore.search)."""
        return self.vectorstore.search(query, top_k=top_k)
