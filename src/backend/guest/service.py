"""Konta gosci wersji testowej: zakladanie z limitem sesji na adres IP,
kasowanie przy wylogowaniu i sprzatanie po GUEST_SESSION_HOURS.

Gosc to zwykly wiersz `users` z is_guest=True i oidc_sub "guest:<losowe>"
(sub z Keycloaka to UUID, wiec nie ma kolizji). Adres IP nie jest zapisywany -
limit sesji z jednego adresu liczy wiersz usage_counters z HMAC adresu
(klucz z AUTH_SECRET_KEY). Ten licznik nie znika przy wylogowaniu ani przy
kasowaniu goscia, wiec "zaloz - zapytaj - wyloguj" nie omija limitu. Adres
IPv6 liczy sie jako cala siec /64 (zmiana adresu w sieci nie daje nowych
sesji). Limit pytan goscia liczy limits/usage.py.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..attachments.storage import remove_files
from ..history import conversation_lock, delete_conversations
from ..limits.usage import consume_counter, guest_address_key, usage_day
from ..models import (
    Attachment,
    Conversation,
    DailyAttachmentUsage,
    DailyUsage,
    MessageFeedback,
    SecurityIncident,
    User,
    UserLimit,
    UserSession,
    UsosLink,
    utcnow,
)
from .settings import GuestSettings, get_guest_settings

logger = logging.getLogger(__name__)

GUEST_SUB_PREFIX = "guest:"
# IPv6: jedna osoba ma zwykle cala siec /64 - liczymy ja jako jeden adres
IPV6_QUOTA_PREFIX = 64
_HASH_CONTEXT = b"chatbot-guest-client-ip:"


class GuestQuotaExceeded(Exception):
    """Z tego adresu IP zalozono dzis juz GUEST_SESSIONS_PER_IP_PER_DAY sesji."""


def _quota_address(raw: str) -> str | None:
    """Adres do limitu: IPv4 bez zmian, IPv6 jako siec /64. None = nie adres."""
    try:
        address = ipaddress.ip_address(raw.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is None:
        return str(ipaddress.ip_network(f"{address}/{IPV6_QUOTA_PREFIX}", strict=False))
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return str(address)


def client_address(forwarded: str | None, peer: str | None) -> str | None:
    """Adres goscia do limitu sesji: naglowek X-Client-IP od nginx (nginx
    ustawia go zawsze - z CF-Connecting-IP albo adresu polaczenia, klient go
    nie nadpisze), a bez naglowka (lokalnie, testy) adres polaczenia.

    None = naglowek jest, ale to nie adres (np. podrobiony CF-Connecting-IP) -
    wolajacy odrzuca zapytanie zamiast liczyc je na wspolny adres nginx.
    """
    if forwarded:
        return _quota_address(forwarded)
    if peer:
        return _quota_address(peer) or "unknown"
    return "unknown"


def client_hash(address: str, secret_key: str) -> str:
    """HMAC-SHA256 adresu (hex) - zapisywany zamiast samego adresu."""
    key = hashlib.sha256(_HASH_CONTEXT + secret_key.encode()).digest()
    return hmac.new(key, address.encode(), hashlib.sha256).hexdigest()


def create_guest(db: Session, address_hash: str, settings: GuestSettings, now: datetime) -> User:
    """Zaklada konto goscia (bez commita konta - commituje create_guest_session).
    Sesja zuzywa miejsce w dziennym limicie adresu od razu i atomowo, wiec
    rownolegle zapytania z jednego adresu go nie przekrocza.

    Raises:
        GuestQuotaExceeded: limit sesji z tego adresu na dzis wyczerpany.
    """
    key = guest_address_key(usage_day(now), address_hash)
    if not consume_counter(db, key, settings.sessions_per_ip_per_day):
        raise GuestQuotaExceeded()
    user = User(
        oidc_sub=GUEST_SUB_PREFIX + secrets.token_hex(16),
        is_guest=True,
        created_at=now,
        last_login_at=now,
    )
    db.add(user)
    db.flush()
    return user


def _delete_guest_conversations(db: Session, user_id: str) -> None:
    """Rozmowy goscia, kazda pod swoja blokada - odpowiedz w toku najpierw sie
    konczy. Jak przy usunieciu rozmowy przez osobe: oceny znikaja, zgloszenia
    zostaja bez wskazania osoby."""
    conversation_ids = list(db.scalars(select(Conversation.id).where(Conversation.user_id == user_id)))
    for conversation_id in conversation_ids:
        with conversation_lock(conversation_id):
            delete_conversations(db, [conversation_id], by_user=True)


def delete_guest(db: Session, user_id: str) -> None:
    """Kasuje konto goscia ze wszystkim, co do niego nalezy, i commituje.

    SQLite nie wymusza kaskad FK, wiec wiersze zalezne ida pierwsze. Incydenty
    (proby obejscia promptu) zostaja dla zarzadu, ale bez wskazania osoby.
    """
    _delete_guest_conversations(db, user_id)
    files = list(db.scalars(select(Attachment.storage_key).where(Attachment.user_id == user_id)))
    db.execute(delete(Attachment).where(Attachment.user_id == user_id))
    db.execute(delete(MessageFeedback).where(MessageFeedback.user_id == user_id, MessageFeedback.reported_at.is_(None)))
    for table in (DailyUsage, DailyAttachmentUsage, UserLimit, UserSession, UsosLink):
        db.execute(delete(table).where(table.user_id == user_id))
    for model in (MessageFeedback, SecurityIncident):
        db.execute(
            update(model).where(model.user_id == user_id).values(user_id=None)
            .execution_options(synchronize_session=False)
        )
    db.execute(delete(User).where(User.id == user_id, User.is_guest.is_(True)))
    db.commit()
    db.expire_all()
    remove_files(files)


def _purge_orphaned_conversations(db: Session) -> int:
    """Rozmowy zapisane przez odpowiedz w toku juz po skasowaniu goscia (konta
    nie ma, a rozmowa wskazuje na nie). Rozmowy bez osoby (NULL) to co innego."""
    orphaned = list(db.scalars(
        select(Conversation.id).where(
            Conversation.user_id.is_not(None),
            Conversation.user_id.not_in(select(User.id)),
        )
    ))
    if orphaned:
        delete_conversations(db, orphaned, by_user=True)
    return len(orphaned)


def purge_expired_guests(
    db: Session, now: datetime | None = None, settings: GuestSettings | None = None
) -> int:
    """Zadanie sprzatajace: konta gosci starsze niz GUEST_SESSION_HOURS (ich
    sesje juz wygasly) i rozmowy po skasowanych gosciach. Blad przy jednym
    gosciu jest logowany i nie zatrzymuje reszty. Zwraca liczbe usunietych kont."""
    current = now if now is not None else utcnow()
    hours = (settings or get_guest_settings()).session_hours
    cutoff = current - timedelta(hours=hours)
    expired = list(db.scalars(select(User.id).where(User.is_guest.is_(True), User.created_at <= cutoff)))
    removed = 0
    for user_id in expired:
        try:
            delete_guest(db, user_id)
            removed += 1
        except Exception:
            db.rollback()
            logger.exception("removing expired guest %s failed", user_id)
    orphaned = _purge_orphaned_conversations(db)
    if removed or orphaned:
        logger.info("removed %d expired guest accounts and %d orphaned conversations", removed, orphaned)
    return removed
