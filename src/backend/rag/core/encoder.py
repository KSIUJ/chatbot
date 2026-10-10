"""
Lokalny encoder tekst -> wektor (sentence-transformers), bez zewnetrznego API.

Domyslny model sdadas/mmlw-roberta-large (polski model embeddingowy MMLW);
inny ustawia RAG_EMBEDDING_MODEL. Modele MMLW/e5 sa asymetryczne: zapytania
koduje sie z prefiksem "zapytanie: ", dokumenty bez prefiksu
(RAG_QUERY_PREFIX / RAG_PASSAGE_PREFIX; pusta zmienna = wartosc domyslna).
Zmiana modelu lub prefiksu dokumentow wymaga ponownego ingestu.
"""

import os

DEFAULT_MODEL_NAME = "sdadas/mmlw-roberta-large"
DEFAULT_QUERY_PREFIX = "zapytanie: "
DEFAULT_PASSAGE_PREFIX = ""


def _default_device() -> str:
    override = os.getenv("RAG_DEVICE")
    if override:
        return override
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except (ImportError, AttributeError):
        pass
    return "cpu"


class Encoder:
    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        query_prefix: str | None = None,
        passage_prefix: str | None = None,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or os.getenv("RAG_EMBEDDING_MODEL") or DEFAULT_MODEL_NAME
        self.query_prefix = (
            query_prefix if query_prefix is not None else (os.getenv("RAG_QUERY_PREFIX") or DEFAULT_QUERY_PREFIX)
        )
        self.passage_prefix = (
            passage_prefix
            if passage_prefix is not None
            else (os.getenv("RAG_PASSAGE_PREFIX") or DEFAULT_PASSAGE_PREFIX)
        )
        self.device = device or _default_device()
        print(f"[encoder] model={self.model_name} device={self.device}")
        self._model = SentenceTransformer(self.model_name, device=self.device)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Koduje liste fragmentow (dokumentow/passages) na wektory."""
        prefixed = [self.passage_prefix + t for t in texts]
        vectors = self._model.encode(
            prefixed,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Koduje zapytanie uzytkownika (inny prefiks niz dokumenty)."""
        vector = self._model.encode(
            self.query_prefix + query, convert_to_numpy=True, normalize_embeddings=True
        )
        return vector.tolist()
