"""Polaczenia kont z USOS w bazie: zapis po polaczeniu, odczyt tokenu do
wywolan w imieniu uzytkownika, oznaczanie odrzuconych tokenow i rozlaczanie.

Odrzucony token (401 z USOS, np. cofniety przez uzytkownika w USOS albo
wygasly) i token, ktorego nie da sie odszyfrowac (zmieniony AUTH_SECRET_KEY,
wiersz przepisany na inne konto), oznaczamy needs_reconnect_at zamiast
kasowac wiersz: /usos/status pokazuje wtedy "polacz ponownie", a blad
konfiguracji klucza aplikacji nie wymaze po cichu wszystkich polaczen.
Oznaczony token nie jest juz uzywany; ponowne polaczenie nadpisuje wiersz.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..auth.crypto import DecryptionError
from ..models import UsosLink, utcnow
from .client import UsosClient, UsosError, UsosUnauthorizedError
from .crypto import UserToken, UsosTokenCipher

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 255
MAX_USOS_ID_LENGTH = 32


def as_utc(value: datetime) -> datetime:
    """SQLite zwraca daty bez strefy mimo DateTime(timezone=True)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def get_link(db: Session, user_id: str) -> UsosLink | None:
    return db.get(UsosLink, user_id)


def save_link(
    db: Session,
    cipher: UsosTokenCipher,
    *,
    user_id: str,
    token: str,
    secret: str,
    usos_user_id: str,
    usos_name: str | None,
    scopes: str,
) -> tuple[UsosLink, UserToken | None]:
    """Zapisuje (albo nadpisuje) polaczenie konta. Zwraca wiersz i poprzedni
    token, jesli byl inny - wolajacy cofa go w USOS po commicie."""
    link = db.get(UsosLink, user_id)
    previous: UserToken | None = None
    if link is None:
        link = UsosLink(user_id=user_id)
        db.add(link)
    else:
        try:
            old = cipher.unseal(user_id, link.token_enc)
        except DecryptionError:
            old = None
        if old is not None and old.token != token:
            previous = old
    link.usos_user_id = usos_user_id[:MAX_USOS_ID_LENGTH]
    link.usos_name = usos_name[:MAX_NAME_LENGTH] if usos_name else None
    link.token_enc = cipher.seal(user_id, token, secret)
    link.scopes = scopes
    link.created_at = utcnow()
    link.last_used_at = None
    link.needs_reconnect_at = None
    db.commit()
    return link, previous


def mark_needs_reconnect(db: Session, user_id: str) -> None:
    """Oznacza polaczenie jako nieuzywalne (patrz docstring modulu)."""
    link = db.get(UsosLink, user_id)
    if link is not None and link.needs_reconnect_at is None:
        link.needs_reconnect_at = utcnow()
        db.commit()
        logger.info("usos link of user %s marked as needing reconnect", user_id)


def get_user_token(db: Session, cipher: UsosTokenCipher, user_id: str) -> UserToken | None:
    """Token USOS konta do wywolan w jego imieniu (czesc 2: narzedzia modelu).

    Returns:
        Token albo None: brak polaczenia, polaczenie do odnowienia, albo
        szyfrogram nie do odczytania / innego konta (wtedy tez oznaczane).
        Udany odczyt aktualizuje last_used_at.
    """
    link = db.get(UsosLink, user_id)
    if link is None or link.needs_reconnect_at is not None:
        return None
    try:
        token = cipher.unseal(user_id, link.token_enc)
    except DecryptionError:
        logger.warning("cannot decrypt usos token of user %s - marking link for reconnect", user_id)
        mark_needs_reconnect(db, user_id)
        return None
    link.last_used_at = utcnow()
    db.commit()
    return token


def usos_user_call(db: Session, client: UsosClient, token: UserToken, method: str, **params: Any) -> Any:
    """Wywolanie USOS API w imieniu uzytkownika (timeout, bez przekierowan,
    bledy jako wyjatki UsosError z client.py).

    Odpowiedz 401 oznacza polaczenie needs_reconnect_at i rzuca dalej
    UsosUnauthorizedError - wolajacy mowi uzytkownikowi, zeby polaczyl sie
    ponownie w Ustawieniach.
    """
    try:
        return client.call(token, method, **params)
    except UsosUnauthorizedError:
        logger.info("usos rejected token of user %s on %s", token.user_id, method)
        mark_needs_reconnect(db, token.user_id)
        raise


def revoke_quietly(client: UsosClient, token: UserToken) -> bool:
    """Cofa token w USOS; blad tylko loguje (bez sekretow). Zwraca, czy sie udalo."""
    try:
        client.revoke(token)
    except UsosError as exc:
        logger.warning("cannot revoke usos token of user %s: %s", token.user_id, type(exc).__name__)
        return False
    return True


def unlink(db: Session, cipher: UsosTokenCipher, client: UsosClient | None, user_id: str) -> bool:
    """Rozlacza konto: cofa token w USOS (jesli jest klient i token da sie
    odczytac; najlepiej jak sie da) i kasuje wiersz. Do uzycia tez przy
    usuwaniu konta. Zwraca, czy polaczenie istnialo."""
    link = db.get(UsosLink, user_id)
    if link is None:
        return False
    token: UserToken | None
    try:
        token = cipher.unseal(user_id, link.token_enc)
    except DecryptionError:
        token = None
    db.delete(link)
    db.commit()
    if client is not None and token is not None:
        revoke_quietly(client, token)
    return True
