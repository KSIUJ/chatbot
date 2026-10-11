"""
Opcjonalny reranker (cross-encoder z sentence-transformers): ocenia pary
(zapytanie, fragment) i ustawia kandydatow puli od najlepszego. Wlacza go
RAG_RERANKER_MODEL (np. sdadas/polish-reranker-base-ranknet); brak zmiennej =
reranker wylaczony, kolejnosc z fuzji RRF zostaje. RAG_RERANKER_MIN_SCORE
odrzuca kandydatow z nizsza ocena (skala zalezy od modelu; brak = bez progu).

Na CPU bez AVX2 (VM produkcyjna) model base potrzebuje ok. 0,7 s na pare
przy obciazonej maszynie - patrz opis PR kroku 4.
"""

from __future__ import annotations

import os
import threading

MODEL_ENV = "RAG_RERANKER_MODEL"
MIN_SCORE_ENV = "RAG_RERANKER_MIN_SCORE"
# najwiecej znakow fragmentu podawanych modelowi (dluzsze sa przycinane)
MAX_CHARS = 1500
MAX_TOKENS = 512
BATCH_SIZE = 16


class Reranker:
    def __init__(self, model_name: str, device: str | None = None, min_score: float | None = None) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self.min_score = min_score
        print(f"[reranker] model={model_name} min_score={min_score}")
        device = device or os.getenv("RAG_DEVICE") or "cpu"
        self._model = CrossEncoder(model_name, device=device, max_length=MAX_TOKENS)

    def scores(self, query: str, texts: list[str]) -> list[float]:
        """Ocena trafnosci kazdego tekstu dla zapytania (wiecej = lepiej)."""
        if not texts:
            return []
        pairs = [(query, text[:MAX_CHARS]) for text in texts]
        return [float(s) for s in self._model.predict(pairs, batch_size=BATCH_SIZE, show_progress_bar=False)]


def _min_score() -> float | None:
    value = os.getenv(MIN_SCORE_ENV, "").strip()
    return float(value) if value else None


_default: Reranker | None = None
_lock = threading.Lock()


def default_reranker() -> Reranker | None:
    """Wspolny reranker procesu albo None, gdy RAG_RERANKER_MODEL nie jest ustawiony."""
    global _default
    model_name = os.getenv(MODEL_ENV, "").strip()
    if not model_name:
        return None
    with _lock:
        if _default is None or _default.model_name != model_name:
            _default = Reranker(model_name, min_score=_min_score())
    return _default
