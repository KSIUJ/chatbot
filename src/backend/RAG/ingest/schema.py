"""
Wspolny, znormalizowany schemat dokumentu uzywany przez caly RAG.

Kazde z trzech zrodel danych (mordor, strony, usos) ma wlasny format wyjsciowy
(patrz from_mordor.py / from_strony.py / from_usos.py) - to jedyne miejsca,
ktore znaja te specyfike. Reszta pipeline'u (encoder, vectorstore, retriever)
operuje wylacznie na obiektach Document ponizej.
"""

import hashlib
from dataclasses import dataclass, field

VALID_SOURCES = ("mordor", "strony", "usos")
VALID_CONTENT_TYPES = ("text", "image")


@dataclass
class Document:
    id: str
    source: str
    embed_text: str
    content_type: str
    value: str
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.source not in VALID_SOURCES:
            raise ValueError(f"Nieznane zrodlo: {self.source!r} (oczekiwano jednego z {VALID_SOURCES})")
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
