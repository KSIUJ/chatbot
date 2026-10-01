"""
Zrodla odpowiedzi pokazywane pod wiadomoscia: strony wydzialu, profile USOS
i pliki z mordora. Lista powstaje z trafien RAG-a, ktore trafily do kontekstu,
i jest zapisywana w Message.sources.
"""

import posixpath
from collections.abc import Iterable
from typing import Literal, TypedDict
from urllib.parse import unquote, urlsplit

SourceKind = Literal["strony", "usos", "mordor"]

_HTTP_SCHEMES = ("http", "https")


class Source(TypedDict):
    kind: SourceKind
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


def _page_title(url: str) -> str:
    """Krotka forma adresu strony: host + sciezka, bez schematu i "/" na koncu."""
    parts = urlsplit(url)
    return unquote(f"{parts.netloc}{parts.path}").rstrip("/")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def source_from_hit(hit: dict) -> Source | None:
    """Zrodlo dla jednego trafienia; None gdy nie ma czego pokazac."""
    metadata = hit.get("metadata") or {}
    kind = hit.get("source")

    if kind == "strony":
        url = http_url(metadata.get("url"))
        return {"kind": "strony", "title": _page_title(url), "url": url} if url else None

    if kind == "usos":
        name = _text(metadata.get("employee_name"))
        if not name:
            return None
        return {"kind": "usos", "title": name, "url": http_url(metadata.get("profile_url"))}

    if kind == "mordor":
        title = _text(metadata.get("source_file")) or _text(metadata.get("file_name"))
        if not title and hit.get("content_type") == "image":
            title = posixpath.basename(_text(hit.get("value")).replace("\\", "/"))
        return {"kind": "mordor", "title": title, "url": None} if title else None

    return None


def collect_sources(hits: Iterable[dict]) -> list[Source]:
    """Zrodla bez powtorzen (kilka fragmentow tej samej strony = jedno zrodlo),
    w kolejnosci trafien."""
    seen: set[tuple[str, str]] = set()
    sources: list[Source] = []
    for hit in hits:
        source = source_from_hit(hit)
        if source is None:
            continue
        key = (source["kind"], source["url"] or source["title"])
        if key in seen:
            continue
        seen.add(key)
        sources.append(source)
    return sources
