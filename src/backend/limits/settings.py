"""Globalne limity: dzienny limit pytan i limity zalacznikow.

Wartosci domyslne pochodza z env (CHAT_DAILY_LIMIT, ATTACHMENT_*), a zarzad
moze je zmienic w panelu administratora - wtedy obowiazuje wiersz w tabeli
app_settings. Zakresy wartosci sa tu w jednym miejscu: uzywa ich parser env
i walidacja API adminow.

Zalaczniki: limity sa juz zapisywane i edytowalne, a egzekwuje je dopiero
funkcja zalacznikow - czyta je jednym wywolaniem get_attachment_limits(db).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Final, Literal, get_args

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AppSetting, utcnow

logger = logging.getLogger(__name__)

# Rodzaj pliku -> (typy MIME, rozszerzenia). "jpeg" obejmuje .jpg i .jpeg.
AttachmentType = Literal["pdf", "docx", "txt", "png", "jpeg", "webp"]
ATTACHMENT_TYPES: Final[dict[str, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    "pdf": (("application/pdf",), (".pdf",)),
    "docx": (("application/vnd.openxmlformats-officedocument.wordprocessingml.document",), (".docx",)),
    "txt": (("text/plain",), (".txt",)),
    "png": (("image/png",), (".png",)),
    "jpeg": (("image/jpeg",), (".jpg", ".jpeg")),
    "webp": (("image/webp",), (".webp",)),
}
ALL_ATTACHMENT_TYPES: Final[tuple[AttachmentType, ...]] = get_args(AttachmentType)


@dataclass(frozen=True)
class IntRange:
    """Dozwolony zakres liczby calkowitej (obustronnie domkniety)."""
    minimum: int
    maximum: int

    def contains(self, value: int) -> bool:
        return self.minimum <= value <= self.maximum


# Globalny limit pytan: 0 wylaczyloby czat wszystkim - do blokowania osoby
# sluzy wyjatek z limitem 0.
DAILY_QUESTION_LIMIT_RANGE = IntRange(1, 1000)
# Wyjatek per osoba: 0 = zablokowany.
USER_DAILY_LIMIT_RANGE = IntRange(0, 1000)
MAX_FILE_MB_RANGE = IntRange(1, 50)
MAX_FILES_PER_MESSAGE_RANGE = IntRange(1, 20)
MAX_ATTACHMENTS_PER_DAY_RANGE = IntRange(0, 500)


@dataclass(frozen=True)
class AttachmentLimits:
    max_file_mb: int
    max_files_per_message: int
    # na osobe na dobe (jak limit pytan); 0 = zalaczniki wylaczone
    max_per_day: int
    allowed_types: tuple[AttachmentType, ...]


@dataclass(frozen=True)
class LimitSettings:
    daily_question_limit: int
    attachments: AttachmentLimits


DEFAULT_LIMITS = LimitSettings(
    daily_question_limit=10,
    attachments=AttachmentLimits(
        max_file_mb=10, max_files_per_message=5, max_per_day=20, allowed_types=ALL_ATTACHMENT_TYPES,
    ),
)

ATTACHMENT_ENV_VARS: Final[tuple[str, ...]] = (
    "ATTACHMENT_MAX_FILE_MB",
    "ATTACHMENT_MAX_FILES_PER_MESSAGE",
    "ATTACHMENT_DAILY_LIMIT",
    "ATTACHMENT_ALLOWED_TYPES",
)

# Klucze w tabeli app_settings
KEY_DAILY_QUESTION_LIMIT = "chat.daily_question_limit"
KEY_MAX_FILE_MB = "attachments.max_file_mb"
KEY_MAX_FILES_PER_MESSAGE = "attachments.max_files_per_message"
KEY_MAX_ATTACHMENTS_PER_DAY = "attachments.max_per_day"
KEY_ALLOWED_TYPES = "attachments.allowed_types"


class LimitsConfigError(RuntimeError):
    """Bledna wartosc CHAT_DAILY_LIMIT / ATTACHMENT_* w env."""


def normalize_types(values: list[str] | tuple[str, ...]) -> tuple[AttachmentType, ...]:
    """Rodzaje plikow bez powtorzen, w kolejnosci podania.

    Raises:
        ValueError: pusta lista albo nieznany rodzaj.
    """
    result: list[AttachmentType] = []
    for raw in values:
        name = raw.strip().lower()
        if name == "jpg":
            name = "jpeg"
        match = next((t for t in ALL_ATTACHMENT_TYPES if t == name), None)
        if match is None:
            raise ValueError(f"nieznany rodzaj pliku: {raw!r}")
        if match not in result:
            result.append(match)
    if not result:
        raise ValueError("podaj co najmniej jeden rodzaj pliku")
    return tuple(result)


def _env_int(env: Mapping[str, str], name: str, default: int, allowed: IntRange) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise LimitsConfigError(f"{name} musi byc liczba calkowita, jest {raw!r}") from None
    if not allowed.contains(value):
        raise LimitsConfigError(f"{name} musi byc w zakresie {allowed.minimum}-{allowed.maximum}")
    return value


def load_default_limits(env: Mapping[str, str]) -> LimitSettings:
    """Wartosci domyslne z env (puste = DEFAULT_LIMITS).

    Raises:
        LimitsConfigError: wartosc spoza zakresu albo nieznany rodzaj pliku.
    """
    base = DEFAULT_LIMITS.attachments
    raw_types = (env.get("ATTACHMENT_ALLOWED_TYPES") or "").strip()
    try:
        types = normalize_types(raw_types.split(",")) if raw_types else base.allowed_types
    except ValueError as exc:
        raise LimitsConfigError(f"ATTACHMENT_ALLOWED_TYPES: {exc}") from None
    return LimitSettings(
        daily_question_limit=_env_int(
            env, "CHAT_DAILY_LIMIT", DEFAULT_LIMITS.daily_question_limit, DAILY_QUESTION_LIMIT_RANGE
        ),
        attachments=AttachmentLimits(
            max_file_mb=_env_int(env, "ATTACHMENT_MAX_FILE_MB", base.max_file_mb, MAX_FILE_MB_RANGE),
            max_files_per_message=_env_int(
                env, "ATTACHMENT_MAX_FILES_PER_MESSAGE", base.max_files_per_message, MAX_FILES_PER_MESSAGE_RANGE
            ),
            max_per_day=_env_int(env, "ATTACHMENT_DAILY_LIMIT", base.max_per_day, MAX_ATTACHMENTS_PER_DAY_RANGE),
            allowed_types=types,
        ),
    )


@lru_cache(maxsize=1)
def get_default_limits() -> LimitSettings:
    """Wartosci domyslne z os.environ (czytane raz; testy czyszcza cache)."""
    return load_default_limits(os.environ)


def _stored_int(stored: Mapping[str, object], key: str, default: int, allowed: IntRange) -> int:
    value = stored.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not allowed.contains(value):
        logger.warning("ignoring invalid app setting %s=%r", key, value)
        return default
    return value


def _stored_types(stored: Mapping[str, object], default: tuple[AttachmentType, ...]) -> tuple[AttachmentType, ...]:
    value = stored.get(KEY_ALLOWED_TYPES)
    if value is None:
        return default
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        logger.warning("ignoring invalid app setting %s=%r", KEY_ALLOWED_TYPES, value)
        return default
    try:
        return normalize_types([str(v) for v in value])
    except ValueError:
        logger.warning("ignoring invalid app setting %s=%r", KEY_ALLOWED_TYPES, value)
        return default


def get_limit_settings(db: Session, defaults: LimitSettings | None = None) -> LimitSettings:
    """Obowiazujace limity: wartosci zapisane przez zarzad, a dla brakujacych
    (albo uszkodzonych - recznie zmieniona baza) wartosci domyslne z env."""
    base = defaults if defaults is not None else get_default_limits()
    stored: dict[str, object] = {
        row.key: row.value for row in db.execute(select(AppSetting)).scalars()
    }
    attachments = base.attachments
    return LimitSettings(
        daily_question_limit=_stored_int(
            stored, KEY_DAILY_QUESTION_LIMIT, base.daily_question_limit, DAILY_QUESTION_LIMIT_RANGE
        ),
        attachments=AttachmentLimits(
            max_file_mb=_stored_int(stored, KEY_MAX_FILE_MB, attachments.max_file_mb, MAX_FILE_MB_RANGE),
            max_files_per_message=_stored_int(
                stored, KEY_MAX_FILES_PER_MESSAGE, attachments.max_files_per_message, MAX_FILES_PER_MESSAGE_RANGE
            ),
            max_per_day=_stored_int(
                stored, KEY_MAX_ATTACHMENTS_PER_DAY, attachments.max_per_day, MAX_ATTACHMENTS_PER_DAY_RANGE
            ),
            allowed_types=_stored_types(stored, attachments.allowed_types),
        ),
    )


def get_attachment_limits(db: Session) -> AttachmentLimits:
    """Limity zalacznikow dla funkcji zalacznikow - jedno wywolanie."""
    return get_limit_settings(db).attachments


def get_daily_question_limit(db: Session) -> int:
    """Globalny dzienny limit pytan (bez wyjatkow per osoba)."""
    return get_limit_settings(db).daily_question_limit


def save_limit_settings(db: Session, settings: LimitSettings, admin_id: str | None) -> LimitSettings:
    """Zapisuje wszystkie globalne limity (pelna zamiana) i commituje.
    Wartosci musza byc juz zwalidowane (schemat API albo load_default_limits)."""
    values: dict[str, int | list[str]] = {
        KEY_DAILY_QUESTION_LIMIT: settings.daily_question_limit,
        KEY_MAX_FILE_MB: settings.attachments.max_file_mb,
        KEY_MAX_FILES_PER_MESSAGE: settings.attachments.max_files_per_message,
        KEY_MAX_ATTACHMENTS_PER_DAY: settings.attachments.max_per_day,
        KEY_ALLOWED_TYPES: list(settings.attachments.allowed_types),
    }
    now = utcnow()
    for key, value in values.items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value, updated_by=admin_id, updated_at=now))
        else:
            row.value = value
            row.updated_by = admin_id
            row.updated_at = now
    db.commit()
    return get_limit_settings(db)
