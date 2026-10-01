import pytest


class FakeEncoder:
    """Prosty, deterministyczny encoder do testow - bez pobierania modelu.

    Embedding oparty o hashing slow (bag-of-words hashing trick): kazde slowo
    wpada do jednego z N koszykow na podstawie hash(), wektor to znormalizowany
    histogram koszykow. Wystarczajaco sensowny, zeby podobne teksty mialy
    podobne wektory (przydatne w testach top-k), bez zadnej zaleznosci od
    sentence-transformers/GPU.
    """

    DIM = 32

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._hash_embed(query)

    def _hash_embed(self, text: str) -> list[float]:
        vector = [0.0] * self.DIM
        for word in text.lower().split():
            bucket = hash(word) % self.DIM
            vector[bucket] += 1.0

        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector


@pytest.fixture
def fake_encoder():
    """FakeEncoder jako fixture - import z modulu "conftest" koliduje, gdy
    pytest zbiera kilka katalogow z wlasnym conftest.py bez __init__.py."""
    return FakeEncoder()
