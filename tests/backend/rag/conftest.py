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

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

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
    """Fixture zamiast bezposredniego 'from conftest import FakeEncoder' -
    ten drugi wzorzec psuje sie, gdy pytest zbiera testy z wielu katalogow
    naraz (tests/data/usos/conftest.py i ten plik maja ta sama nazwe modulu
    "conftest" bez __init__.py po drodze, wiec importy kolidują w
    sys.modules). Fixture jest rozwiazywana przez mechanizm DI pytest, nie
    przez zwykly import, wiec nie ma tego problemu."""
    return FakeEncoder()
