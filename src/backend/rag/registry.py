"""
Rejestr RAG-a: ktore zrodla sa wlaczone i jak dziela miejsce w kontekscie.

Pula to grupa zrodel wyszukiwana razem (wektory + BM25), z wlasnym budzetem
znakow i naglowkiem sekcji w kontekscie - Mordor ma osobna pule, zeby duzo
wiekszy zbior notatek nie zagluszal zrodel oficjalnych. Kolejnosc sekcji:
najpierw dokladne wyszukiwania zrodel (np. PRACOWNIK), potem pule w
kolejnosci POOLS. Nowe zrodlo = pakiet w sources/ i wpis tutaj.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sources.base import RagSource
from .sources.ksi import KsiSource
from .sources.mordor import MordorSource
from .sources.uj_pages import UjPagesSource
from .sources.usos import UsosSource

# Naglowki sekcji wewnatrz bloku KONTEKST - ich nazwy (ZRODLA OFICJALNE, DANE Z USOS,
# INFORMACJE KSI, MATERIALY STUDENCKIE) opisuje prompt systemowy (llm/generate.py, zasada 5);
# zmieniaja sie tylko razem z nim.
OFFICIAL_HEADER = "ŹRÓDŁA OFICJALNE (strony UJ i wydziału - wiarygodne):"
USOS_HEADER = (
    "DANE Z USOS (przedmioty i plan zajęć, kierunki, kalendarz akademicki, rejestracje, aktualności, "
    "budynki i sale - wiarygodne, stan z dnia pobrania):"
)
KSI_HEADER = "INFORMACJE KSI (strony i notatki koła - wiarygodne):"
MORDOR_HEADER = "MATERIAŁY STUDENCKIE (Mordor - notatki i skany, mogą zawierać błędy lub być nieaktualne):"


@dataclass(frozen=True)
class Pool:
    name: str
    sources: tuple[str, ...]
    # najwiecej fragmentow puli w kontekscie (sasiednie chunki jednego
    # dokumentu sklejone w jeden fragment licza sie raz)
    k: int
    header: str
    # budzet znakow tekstu puli: kolejne fragmenty dochodza, dopoki sie mieszcza
    budget: int = 4000
    # tyle fragmentow wchodzi nawet ponad budzet (jesli przeszly prog trafnosci)
    min_hits: int = 1
    # najwiecej chunkow jednego dokumentu (strona, plik, karta pracownika)
    per_document: int = 2
    # kandydaci z kazdej listy (wektory, BM25) przed fuzja RRF
    candidates: int = 20


POOLS: tuple[Pool, ...] = (
    Pool("official", ("uj_pages",), k=5, header=OFFICIAL_HEADER, budget=3500),
    # USOS osobno: ponad tysiac fragmentow przedmiotow i budynkow o podobnej budowie
    # zagluszalby strony wydzialu we wspolnej puli
    Pool("usos", ("usos",), k=4, header=USOS_HEADER, budget=2500),
    Pool("ksi", ("ksi",), k=3, header=KSI_HEADER, budget=1500),
    Pool("student", ("mordor",), k=4, header=MORDOR_HEADER, budget=2000),
)


def create_sources() -> dict[str, RagSource]:
    """Nowe instancje wlaczonych zrodel (zrodlo moze trzymac stan, np. slownik
    nazwisk - kazdy retriever ma wlasne)."""
    sources: list[RagSource] = [UjPagesSource(), UsosSource(), MordorSource(), KsiSource()]
    return {source.name: source for source in sources}
