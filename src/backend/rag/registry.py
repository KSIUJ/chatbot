"""
Rejestr RAG-a: ktore zrodla sa wlaczone i jak dziela miejsce w kontekscie.

Pula to grupa zrodel wyszukiwana razem (wektory + BM25), z wlasna liczba
miejsc i naglowkiem sekcji w kontekscie - Mordor ma osobna pule, zeby duzo
wiekszy zbior notatek nie zagluszal zrodel oficjalnych. Kolejnosc sekcji:
najpierw dokladne wyszukiwania zrodel (np. PRACOWNIK), potem pule w
kolejnosci POOLS. Nowe zrodlo = pakiet w sources/ i wpis tutaj.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sources.base import RagSource
from .sources.mordor import MordorSource
from .sources.strony import StronySource
from .sources.usos import UsosSource

# Naglowki sekcji wewnatrz bloku KONTEKST - nazwy zrodel oficjalnych i
# materialow studenckich z Mordoru wystepuja w prompcie systemowym (llm/generate.py).
OFFICIAL_HEADER = "ZRODLA OFICJALNE (strony wydzialu, USOS - wiarygodne):"
MORDOR_HEADER = "MATERIALY STUDENCKIE (Mordor - notatki i skany, moga zawierac bledy lub byc nieaktualne):"


@dataclass(frozen=True)
class Pool:
    name: str
    sources: tuple[str, ...]
    # ile trafien z puli trafia do kontekstu
    k: int
    header: str


POOLS: tuple[Pool, ...] = (
    Pool("official", ("strony", "usos"), k=5, header=OFFICIAL_HEADER),
    Pool("student", ("mordor",), k=5, header=MORDOR_HEADER),
)


def create_sources() -> dict[str, RagSource]:
    """Nowe instancje wlaczonych zrodel (zrodlo moze trzymac stan, np. slownik
    nazwisk - kazdy retriever ma wlasne)."""
    sources: list[RagSource] = [StronySource(), UsosSource(), MordorSource()]
    return {source.name: source for source in sources}
