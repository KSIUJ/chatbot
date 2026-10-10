"""
Dokument w indeksie RAG - wspolny format wszystkich zrodel.

Kazde zrodlo (src/backend/rag/sources/) zamienia swoje dane na Document;
rdzen (encoder, vectorstore, indeks leksykalny, retrieval) zna tylko ten
format. Nazwa zrodla w `source` musi byc zarejestrowana (rag/registry.py) -
sprawdza to ingest.
"""

import hashlib
from dataclasses import dataclass, field

VALID_CONTENT_TYPES = ("text", "image")


@dataclass
class Document:
    id: str
    source: str
    # tekst do wyszukiwania (wektory i BM25)
    embed_text: str
    content_type: str
    # tresc dla modelu (text) albo sciezka pliku (image)
    value: str
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.source:
            raise ValueError("Dokument bez zrodla")
        if self.content_type not in VALID_CONTENT_TYPES:
            raise ValueError(
                f"Nieznany content_type: {self.content_type!r} (oczekiwano jednego z {VALID_CONTENT_TYPES})"
            )


def make_id(source: str, *parts: str) -> str:
    """Generuje stabilne, deterministyczne ID dla dokumentu.

    Deterministyczne (a nie losowe uuid4), zeby ponowny ingest tych samych
    danych zrodlowych nadpisywal istniejace wpisy w vectorstore zamiast je
    duplikowac.
    """
    raw = "|".join((source, *parts))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{source}_{digest}"
