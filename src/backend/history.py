"""Historia rozmow w sidebarze: lista, usuwanie, limit rozmow na konto i
kasowanie rozmow nieuzywanych dluzej niz CHAT_HISTORY_RETENTION_DAYS.

Limity wynikaja z minimalizacji danych (w czacie ludzie wpisuja rozne rzeczy),
nie z miejsca na dysku - tekst rozmow zajmuje ulamek bazy.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Conversation, Message

load_dotenv()

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = 80


class HistoryConfigError(RuntimeError):
    """Bledna wartosc CHAT_HISTORY_* w env."""


@dataclass(frozen=True)
class HistorySettings:
    max_per_user: int
    retention_days: int
    purge_interval_hours: float


def load_history_settings(env: Mapping[str, str]) -> HistorySettings:
    """Czyta limity historii z env (wartosci domyslne: 10 rozmow, 30 dni, co 6 h).

    Raises:
        HistoryConfigError: wartosc nie jest dodatnia liczba.
    """
    def positive(name: str, default: float, cast: Callable[[str], float]) -> float:
        raw = (env.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = cast(raw)
        except ValueError:
            raise HistoryConfigError(f"{name} musi byc liczba, jest {raw!r}") from None
        if value <= 0:
            raise HistoryConfigError(f"{name} musi byc dodatnie")
        return value

    return HistorySettings(
        max_per_user=int(positive("CHAT_HISTORY_MAX_PER_USER", 10, int)),
        retention_days=int(positive("CHAT_HISTORY_RETENTION_DAYS", 30, int)),
        purge_interval_hours=positive("CHAT_HISTORY_PURGE_INTERVAL_HOURS", 6.0, float),
    )


@lru_cache(maxsize=1)
def get_history_settings() -> HistorySettings:
    """Ustawienia z os.environ. Dependency FastAPI - testy podmieniaja je
    przez app.dependency_overrides."""
    return load_history_settings(os.environ)


def make_title(question: str) -> str:
    """Tytul rozmowy: pierwsze pytanie w jednej linii, skrocone do TITLE_MAX_LENGTH."""
    text = " ".join(question.split())
    if len(text) <= TITLE_MAX_LENGTH:
        return text
    return text[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


def list_user_conversations(db: Session, user_id: str, limit: int) -> list[Conversation]:
    """Najnowsze rozmowy uzytkownika (wg ostatniej wiadomosci)."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.last_message_at.desc(), Conversation.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


# Rownolegle zapytania o te sama rozmowe (stop + ponow, dwie karty, usuwanie w
# trakcie generowania) ida po kolei - bez tego powstaja podwojne odpowiedzi
# albo wiadomosci osierocone po usunieciu rozmowy. Stala pula paskowanych
# blokad, w obrebie jednego procesu (backend ma jednego workera).
_CONVERSATION_LOCKS: tuple[threading.Lock, ...] = tuple(threading.Lock() for _ in range(64))


def conversation_lock(conversation_id: str) -> threading.Lock:
    return _CONVERSATION_LOCKS[zlib.crc32(conversation_id.encode()) % len(_CONVERSATION_LOCKS)]


# Duze listy id kasujemy partiami - SQLite ma limit parametrow w zapytaniu.
DELETE_BATCH_SIZE = 500


def delete_conversations(db: Session, conversation_ids: Sequence[str]) -> int:
    """Kasuje rozmowy razem z wiadomosciami (SQLite nie wymusza kaskad FK,
    wiec wiadomosci ida pierwsze). Zwraca liczbe usunietych rozmow."""
    ids = list(conversation_ids)
    deleted = 0
    for start in range(0, len(ids), DELETE_BATCH_SIZE):
        batch = ids[start:start + DELETE_BATCH_SIZE]
        db.execute(delete(Message).where(Message.conversation_id.in_(batch)))
        result = db.execute(delete(Conversation).where(Conversation.id.in_(batch)))
        deleted += int(result.rowcount or 0)
    db.commit()
    return deleted


def delete_user_conversation(db: Session, user_id: str, conversation_id: str) -> bool:
    """Usuwa rozmowe, jesli nalezy do uzytkownika. False = brak takiej rozmowy
    albo cudza (endpoint odpowiada wtedy tak samo: 404). Czeka, az ewentualne
    generowanie odpowiedzi w tej rozmowie sie skonczy."""
    with conversation_lock(conversation_id):
        conversation = db.get(Conversation, conversation_id, populate_existing=True)
        if conversation is None or conversation.user_id != user_id:
            return False
        return delete_conversations(db, [conversation_id]) == 1


def make_room_for_new_conversation(db: Session, user_id: str, max_per_user: int) -> int:
    """Przed zalozeniem nowej rozmowy kasuje najstarsze tak, zeby po jej
    dodaniu uzytkownik mial co najwyzej max_per_user rozmow."""
    stmt = (
        select(Conversation.id)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.last_message_at.desc(), Conversation.created_at.desc())
        .offset(max_per_user - 1)
    )
    return delete_conversations(db, list(db.execute(stmt).scalars()))


def purge_expired_conversations(
    db: Session, retention_days: int, now: datetime | None = None
) -> int:
    """Kasuje rozmowy (takze stare anonimowe) bez nowej wiadomosci od retention_days."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    expired = select(Conversation.id).where(Conversation.last_message_at < cutoff)
    # podzapytanie zamiast listy id - dowolnie duza zaleglosc w jednym DELETE
    db.execute(delete(Message).where(Message.conversation_id.in_(expired)))
    result = db.execute(delete(Conversation).where(Conversation.last_message_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)


def _purge_once(session_factory: Callable[[], Session], retention_days: int) -> None:
    db = session_factory()
    try:
        deleted = purge_expired_conversations(db, retention_days)
        if deleted:
            logger.info("history retention: deleted %d conversation(s) older than %d days", deleted, retention_days)
    except Exception:
        # nie zabijamy petli - sprobujemy przy nastepnym obrocie
        logger.exception("history retention purge failed")
        db.rollback()
    finally:
        db.close()


async def retention_loop(session_factory: Callable[[], Session], settings: HistorySettings) -> None:
    """Czysci wygasle rozmowy przy starcie i potem co purge_interval_hours.
    Backend chodzi na jednym workerze, wiec petla dziala raz na instancje."""
    while True:
        await asyncio.to_thread(_purge_once, session_factory, settings.retention_days)
        await asyncio.sleep(settings.purge_interval_hours * 3600)
