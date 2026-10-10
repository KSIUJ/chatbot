"""
Zrodla odpowiedzi pokazywane pod wiadomoscia (Citation): strony wydzialu,
profile USOS i pliki z mordora. Kazde zrodlo RAG-a samo zamienia swoje
trafienie na Citation (RagSource.cite); tu jest wspolny typ, pomocnicze
funkcje i zbieranie listy bez powtorzen. Lista jest zapisywana w
Message.sources.
"""

from collections.abc import Callable, Iterable
from typing import Literal, TypedDict
from urllib.parse import unquote, urlsplit

# Nazwy zrodel, ktore moga sie pojawic w zapisanych odpowiedziach (Message.sources
# i odpowiedzi API) - test rejestru pilnuje zgodnosci z rag/registry.py. "strony"
# to dawna nazwa uj_pages - zostaje dla odpowiedzi zapisanych przed zmiana.
CitationKind = Literal["uj_pages", "usos", "mordor", "ksi", "strony"]

_HTTP_SCHEMES = ("http", "https")


class Citation(TypedDict):
    kind: CitationKind
    title: str
    url: str | None


def http_url(value: object) -> str | None:
    """Adres tylko gdy to http(s) z hostem - inne (javascript:, file:) odpadaja."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    parts = urlsplit(url)
    if parts.scheme.lower() not in _HTTP_SCHEMES or not parts.netloc:
        return None
    return url


def page_title(url: str) -> str:
    """Krotka forma adresu strony: host + sciezka, bez schematu i "/" na koncu."""
    parts = urlsplit(url)
    return unquote(f"{parts.netloc}{parts.path}").rstrip("/")


def text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def collect_citations(hits: Iterable[dict], cite: Callable[[dict], Citation | None]) -> list[Citation]:
    """Zrodla bez powtorzen (kilka fragmentow tej samej strony = jedno zrodlo),
    w kolejnosci trafien."""
    seen: set[tuple[str, str]] = set()
    citations: list[Citation] = []
    for hit in hits:
        citation = cite(hit)
        if citation is None:
            continue
        key = (citation["kind"], citation["url"] or citation["title"])
        if key in seen:
            continue
        seen.add(key)
        citations.append(citation)
    return citations
