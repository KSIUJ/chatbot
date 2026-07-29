"""
Lokalny encoder tekst -> wektor (embeddingi), bez zaleznosci od zadnego API.

Wybor modelu: sdadas/mmlw-roberta-large (domyslnie) - dedykowany model
embeddingowy dla jezyka polskiego z projektu MMLW (OPI PIB / ICM), publicznie
dostepny na HuggingFace i uruchamiany lokalnie przez sentence-transformers,
co jest spojne z reszta stosu (lokalny LLM Qwen, bez kluczy API). Domyslny
`all-MiniLM-L6-v2` jest trenowany glownie na danych angielskich i wypada
zauwazalnie slabiej na polskich zdaniach - patrz benchmark PIRB
(https://huggingface.co/spaces/sdadas/pirb), gdzie modele MMLW gora nad
ogolnymi modelami wielojezycznymi na polskich zadaniach retrieval.

Jesli materialy z mordoru okaza sie w znacznej czesci anglojezyczne (do
zweryfikowania w kroku 0 - w momencie pisania tego modulu w data/mordor/ nie
bylo jeszcze zadnych realnych plikow), rozsadna alternatywa to
`intfloat/multilingual-e5-large` lub `BAAI/bge-m3` (oba wielojezyczne,
wymagaja tego samego prefiksu query/passage co e5). Model mozna podmienic bez
zmian w kodzie przez zmienna srodowiskowa RAG_EMBEDDING_MODEL.

Modele w rodzinie MMLW/e5 sa asymetryczne: query i dokumenty koduje sie z
innym prefiksem tekstowym. Domyslne prefiksy ponizej odpowiadaja konwencji
MMLW/e5 ("zapytanie: " dla zapytan, brak prefiksu dla dokumentow) - jesli
podmienimy model na jeden bez tej konwencji, oba prefiksy nalezy ustawic na "".
"""

import os

DEFAULT_MODEL_NAME = "sdadas/mmlw-roberta-large"
DEFAULT_QUERY_PREFIX = "zapytanie: "
DEFAULT_PASSAGE_PREFIX = ""


class Encoder:
    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        query_prefix: str | None = None,
        passage_prefix: str | None = None,
    ):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_MODEL_NAME)
        self.query_prefix = (
            query_prefix if query_prefix is not None else os.getenv("RAG_QUERY_PREFIX", DEFAULT_QUERY_PREFIX)
        )
        self.passage_prefix = (
            passage_prefix
            if passage_prefix is not None
            else os.getenv("RAG_PASSAGE_PREFIX", DEFAULT_PASSAGE_PREFIX)
        )
        self._model = SentenceTransformer(self.model_name, device=device)

    def embed(self, text: str) -> list[float]:
        """Koduje pojedynczy fragment (dokument/passage) na wektor."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Koduje liste fragmentow (dokumentow/passages) na wektory."""
        prefixed = [self.passage_prefix + t for t in texts]
        vectors = self._model.encode(prefixed, convert_to_numpy=True, normalize_embeddings=True)
        return vectors.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Koduje zapytanie uzytkownika (inny prefiks niz dokumenty)."""
        vector = self._model.encode(
            self.query_prefix + query, convert_to_numpy=True, normalize_embeddings=True
        )
        return vector.tolist()
