"""
Baza wektorowa (ChromaDB, PersistentClient) dla RAG.

Jedna kolekcja dla wszystkich trzech zrodel danych (mordor/strony/usos) -
zrodlo jest zapisane w metadanych kazdego wpisu (`source`), zeby retrieval
przeszukiwal wszystko naraz zamiast osobnych indeksow per zrodlo.

Dane trzymane sa w dataset/vectorstore/ (katalog `dataset/` jest juz
przygotowany w repo pod docelowy znormalizowany dataset - patrz README).
"""

import os

from .encoder import Encoder
from .ingest.schema import Document

DEFAULT_PERSIST_DIR = os.path.join("dataset", "vectorstore")
COLLECTION_NAME = "chatbot_wmi"

GROUP_MORDOR = {"source": "mordor"}
GROUP_OTHER = {"source": {"$in": ["strony", "usos"]}}


class VectorStore:
    def __init__(self, persist_dir: str = DEFAULT_PERSIST_DIR, encoder: Encoder | None = None):
        import chromadb

        self.persist_dir = persist_dir
        self.encoder = encoder or Encoder()

        os.makedirs(self.persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)

    def add_documents(self, documents: list[Document]) -> None:
        """Embeduje i dodaje dokumenty do kolekcji (upsert po Document.id)."""
        if not documents:
            return

        embeddings = self.encoder.embed_batch([doc.embed_text for doc in documents])
        ids = [doc.id for doc in documents]
        values = [doc.value for doc in documents]
        metadatas = [
            {**doc.metadata, "source": doc.source, "content_type": doc.content_type}
            for doc in documents
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=values,
            metadatas=metadatas,
        )

    def filter_new(self, documents: list[Document]) -> list[Document]:
        if not documents:
            return []

        ids = [d.id for d in documents]
        present: set[str] = set()
        for i in range(0, len(ids), 1000):
            got = self._collection.get(ids=ids[i : i + 1000])
            present.update(got.get("ids", []))

        return [d for d in documents if d.id not in present]

    @property
    def collection(self):
        return self._collection

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []

        got = self._collection.get(ids=ids, include=["documents", "metadatas"])
        by_id = {}
        for id_, value, metadata in zip(got["ids"], got["documents"], got["metadatas"]):
            by_id[id_] = {
                "id": id_,
                "value": value,
                "content_type": metadata.get("content_type", "text"),
                "source": metadata.get("source"),
                "metadata": metadata,
                "distance": None,
            }
        return [by_id[i] for i in ids if i in by_id]

    def _query(self, embedding: list[float], top_k: int, where: dict | None = None) -> list[dict]:
        if top_k <= 0:
            return []

        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
        )

        hits = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for id_, value, metadata, distance in zip(ids, documents, metadatas, distances):
            hits.append(
                {
                    "id": id_,
                    "value": value,
                    "content_type": metadata.get("content_type", "text"),
                    "source": metadata.get("source"),
                    "metadata": metadata,
                    "distance": distance,
                }
            )
        return hits

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Zwraca top-k najbardziej pasujacych wpisow dla danego zapytania."""
        return self._query(self.encoder.embed_query(query), top_k)

    def search_split(
        self, query: str, k_mordor: int = 5, k_other: int = 5
    ) -> dict[str, list[dict]]:
        embedding = self.encoder.embed_query(query)
        return {
            "mordor": self._query(embedding, k_mordor, GROUP_MORDOR),
            "other": self._query(embedding, k_other, GROUP_OTHER),
        }

    def count(self) -> int:
        return self._collection.count()
