"""Pliki zalacznikow na dysku: katalog ATTACHMENTS_DIR (domyslnie "uploads",
w Dockerze wolumen chatbot-uploads), losowe nazwy i bezpieczne kasowanie.

Nazwa pliku na dysku to zawsze 32 znaki hex (secrets.token_hex), w trakcie
wysylania z koncowka ".part". Nazwa od uzytkownika nigdy nie trafia do
sciezki, a kasowanie odrzuca wszystko, co nie pasuje do tego wzorca.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from collections.abc import Collection, Iterable
from datetime import datetime
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

DEFAULT_ATTACHMENTS_DIR: Final = "uploads"
PART_SUFFIX: Final = ".part"
_KEY_PATTERN: Final = re.compile(r"^[0-9a-f]{32}(?:\.part)?$")


def attachments_dir() -> Path:
    """Katalog z plikami (env ATTACHMENTS_DIR, czytany przy kazdym uzyciu)."""
    return Path(os.getenv("ATTACHMENTS_DIR", "").strip() or DEFAULT_ATTACHMENTS_DIR)


def new_storage_key() -> str:
    return secrets.token_hex(16)


def is_storage_name(name: str) -> bool:
    return bool(_KEY_PATTERN.fullmatch(name))


def path_for(name: str) -> Path:
    """Sciezka pliku o nazwie z new_storage_key() (opcjonalnie z ".part").

    Raises:
        ValueError: nazwa spoza wzorca (np. "../cos").
    """
    if not is_storage_name(name):
        raise ValueError(f"invalid attachment storage name: {name!r}")
    return attachments_dir() / name


def remove_files(names: Iterable[str]) -> int:
    """Kasuje pliki o podanych nazwach; zwraca liczbe usunietych. Bledy sa
    logowane i nie przerywaja pracy - wiersz w bazie i tak juz zniknal,
    a zablakane pliki sprzata purge (sweep_stray_files)."""
    removed = 0
    for name in names:
        try:
            path = path_for(name)
        except ValueError:
            logger.warning("refusing to delete attachment file with invalid name %r", name)
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError as exc:
            logger.warning("deleting attachment file %s failed: %s", name, exc)
    return removed


def sweep_stray_files(known: Collection[str], older_than: datetime) -> int:
    """Kasuje pliki bez wiersza w bazie (np. przerwane wysylanie) starsze niz
    older_than. Mlodsze zostaja - moga byc wlasnie wysylane."""
    root = attachments_dir()
    if not root.is_dir():
        return 0
    cutoff = older_than.timestamp()
    stray: list[str] = []
    for entry in root.iterdir():
        name = entry.name
        if not is_storage_name(name) or name in known or not entry.is_file():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                stray.append(name)
        except OSError as exc:
            logger.warning("checking attachment file %s failed: %s", name, exc)
    return remove_files(stray)
