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

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Zwraca top-k najbardziej pasujacych wpisow dla danego zapytania."""
        query_embedding = self.encoder.embed_query(query)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
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

    def count(self) -> int:
        return self._collection.count()
