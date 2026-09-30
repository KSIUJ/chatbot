"""Logika sesji: zakladanie kont z danych Keycloaka, sesje w bazie i
sprawdzanie czlonkostwa w grupie przy kazdym zapytaniu."""

from __future__ import annotations

import logging
import threading
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..database import get_user_by_oidc_sub
from ..models import User, UserSession, utcnow
from .crypto import DecryptionError, TokenCipher, hash_session_token, new_session_token
from .oidc import (
    InvalidGrantError,
    JSONObject,
    OIDCClient,
    TokenSet,
    UserinfoUnauthorizedError,
)
from .settings import AuthSettings

logger = logging.getLogger(__name__)

# Access token odswiezamy troche przed wygasnieciem, zeby nie trafic w userinfo
# tokenem, ktory wygasa w trakcie zapytania.
ACCESS_TOKEN_REFRESH_MARGIN = timedelta(seconds=30)

# Blokady per sesja (paskowane - stala pula, bez wycieku pamieci). Dwa
# rownolegle zapytania tej samej sesji nie moga odswiezac tokenow naraz: przy
# wlaczonej rotacji refresh tokenow w Keycloaku drugie uzyloby juz
# uniewaznionego tokenu i wylogowalo uzytkownika. Dziala w obrebie jednego
# procesu - backend startuje z jednym workerem uvicorna.
_SESSION_LOCKS: tuple[threading.Lock, ...] = tuple(threading.Lock() for _ in range(64))


def _lock_for(session_id: str) -> threading.Lock:
    return _SESSION_LOCKS[int(session_id[:8], 16) % len(_SESSION_LOCKS)]


def _as_utc(value: datetime) -> datetime:
    """SQLite zwraca daty bez strefy mimo DateTime(timezone=True)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class AuthFailure(Exception):
    """Zapytanie nie moze byc obsluzone jako zalogowany czlonek KSI.

    `code` trafia do frontendu (detail.code) i decyduje o komunikacie.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _not_authenticated() -> AuthFailure:
    return AuthFailure(401, "not_authenticated", "Zaloguj sie kontem KSI.")


def _session_expired() -> AuthFailure:
    return AuthFailure(401, "session_expired", "Sesja wygasla - zaloguj sie ponownie.")


def _not_member() -> AuthFailure:
    return AuthFailure(403, "not_member", "Chatbot jest dostepny tylko dla czlonkow KSI.")


# --- grupy ---------------------------------------------------------------

def extract_groups(claims: JSONObject, claim_name: str) -> set[str]:
    """Grupy z claimu (lista napisow), znormalizowane do NFC."""
    raw = claims.get(claim_name)
    if not isinstance(raw, list):
        return set()
    return {unicodedata.normalize("NFC", g) for g in raw if isinstance(g, str)}


def is_member(claims: JSONObject, settings: AuthSettings) -> bool:
    """Czy claimy (z userinfo) zawieraja wymagana grupe, np. /Członek."""
    return settings.required_group in extract_groups(claims, settings.groups_claim)


# --- uzytkownicy -----------------------------------------------------------

def _claim_str(claims: JSONObject, key: str, max_len: int) -> str | None:
    value = claims.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:max_len]


def _apply_profile(user: User, claims: JSONObject) -> None:
    """Kopiuje dane profilu z claimow; brakujacy claim nie kasuje wartosci."""
    email = _claim_str(claims, "email", 255)
    username = _claim_str(claims, "preferred_username", 100)
    name = _claim_str(claims, "name", 255)
    if email is not None:
        user.email = email.lower()
    if username is not None:
        user.username = username
    if name is not None:
        user.name = name


def upsert_user(db: Session, sub: str, claims: JSONObject) -> User:
    """Zwraca konto dla `sub`, zakladajac je przy pierwszym logowaniu.
    Konta sa wiazane wylacznie po `sub` - nigdy po emailu."""
    user = get_user_by_oidc_sub(db, sub)
    if user is None:
        user = User(oidc_sub=sub)
        db.add(user)
    _apply_profile(user, claims)
    user.last_login_at = utcnow()
    db.flush()
    return user


# --- sesje -----------------------------------------------------------------

def _store_tokens(session: UserSession, tokens: TokenSet, cipher: TokenCipher) -> None:
    session.access_token_enc = cipher.encrypt(tokens.access_token)
    session.access_token_expires_at = tokens.access_token_expires_at
    # Keycloak moze nie zwrocic nowego refresh/id tokenu przy odswiezeniu -
    # wtedy zostaja poprzednie.
    if tokens.refresh_token is not None:
        session.refresh_token_enc = cipher.encrypt(tokens.refresh_token)
    if tokens.id_token is not None:
        session.id_token_enc = cipher.encrypt(tokens.id_token)


def create_session(
    db: Session,
    user: User,
    tokens: TokenSet,
    cipher: TokenCipher,
    settings: AuthSettings,
) -> str:
    """Zaklada sesje i zwraca surowy token do ciasteczka (w bazie jest tylko hash).
    Zawsze nowy token - brak session fixation."""
    raw_token = new_session_token()
    now = utcnow()
    session = UserSession(
        id=hash_session_token(raw_token),
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=settings.session_max_age_seconds),
    )
    _store_tokens(session, tokens, cipher)
    db.add(session)
    db.commit()
    return raw_token


def find_session(db: Session, raw_token: str) -> UserSession | None:
    """Sesja dla tokenu z ciasteczka; wygasla jest kasowana i daje None."""
    session = db.get(UserSession, hash_session_token(raw_token))
    if session is None:
        return None
    if _as_utc(session.expires_at) <= utcnow():
        db.delete(session)
        db.commit()
        return None
    return session


def delete_session(db: Session, session: UserSession) -> None:
    db.delete(session)
    db.commit()


def purge_expired_sessions(db: Session) -> int:
    """Sprzata wygasle sesje (wywolywane przy logowaniu)."""
    result = db.execute(delete(UserSession).where(UserSession.expires_at <= utcnow()))
    db.commit()
    return int(result.rowcount or 0)


def decrypt_id_token(session: UserSession, cipher: TokenCipher) -> str | None:
    if session.id_token_enc is None:
        return None
    try:
        return cipher.decrypt(session.id_token_enc)
    except DecryptionError:
        return None


def _refresh_tokens(
    db: Session,
    session: UserSession,
    oidc: OIDCClient,
    cipher: TokenCipher,
) -> str:
    """Odswieza tokeny sesji i zwraca nowy access token.

    Raises:
        AuthFailure: gdy sesji nie da sie odswiezyc (sesja jest kasowana).
        ProviderUnavailableError: Keycloak niedostepny (sesja zostaje).
    """
    if session.refresh_token_enc is None:
        delete_session(db, session)
        raise _session_expired()
    try:
        refresh_token = cipher.decrypt(session.refresh_token_enc)
    except DecryptionError:
        # np. zmieniony AUTH_SECRET_KEY - stare sesje sa bezuzyteczne
        delete_session(db, session)
        raise _session_expired() from None
    try:
        tokens = oidc.refresh(refresh_token)
    except InvalidGrantError:
        delete_session(db, session)
        raise _session_expired() from None
    _store_tokens(session, tokens, cipher)
    db.commit()
    return tokens.access_token


def _current_access_token(
    db: Session,
    session: UserSession,
    oidc: OIDCClient,
    cipher: TokenCipher,
) -> str:
    if _as_utc(session.access_token_expires_at) - ACCESS_TOKEN_REFRESH_MARGIN <= utcnow():
        return _refresh_tokens(db, session, oidc, cipher)
    try:
        return cipher.decrypt(session.access_token_enc)
    except DecryptionError:
        return _refresh_tokens(db, session, oidc, cipher)


def authenticate(
    db: Session,
    raw_token: str | None,
    oidc: OIDCClient,
    cipher: TokenCipher,
    settings: AuthSettings,
) -> User:
    """Sprawdza sesje z ciasteczka i - przy kazdym zapytaniu - aktualne
    czlonkostwo w grupie przez userinfo Keycloaka.

    Usuniecie z grupy, zablokowanie konta albo wylogowanie w Keycloaku odbiera
    dostep przy najblizszym zapytaniu, bez czekania na wygasniecie sesji.

    Raises:
        AuthFailure: 401 (brak/wygasla sesja) albo 403 (brak w grupie).
        ProviderUnavailableError: Keycloak niedostepny - wolajacy zwraca 503
            (fail closed: bez potwierdzenia czlonkostwa nie wpuszczamy).
    """
    if not raw_token:
        raise _not_authenticated()
    session = find_session(db, raw_token)
    if session is None:
        raise _session_expired()

    with _lock_for(session.id):
        # Inne zapytanie moglo w miedzyczasie odswiezyc tokeny albo skasowac sesje.
        session = db.get(UserSession, session.id, populate_existing=True)
        if session is None:
            raise _session_expired()
        user = session.user
        if not user.is_active:
            delete_session(db, session)
            raise _session_expired()

        access_token = _current_access_token(db, session, oidc, cipher)
        try:
            claims = oidc.userinfo(access_token)
        except UserinfoUnauthorizedError:
            # Token odrzucony przed swoim expiry (np. restart Keycloaka) -
            # jedna proba z odswiezonym tokenem, potem koniec sesji.
            access_token = _refresh_tokens(db, session, oidc, cipher)
            try:
                claims = oidc.userinfo(access_token)
            except UserinfoUnauthorizedError:
                delete_session(db, session)
                raise _session_expired() from None

        if claims.get("sub") != user.oidc_sub:
            logger.warning("userinfo sub mismatch for user %s - dropping session", user.id)
            delete_session(db, session)
            raise _session_expired()
        if not is_member(claims, settings):
            logger.info("user %s is no longer in %s - dropping session", user.id, settings.required_group)
            delete_session(db, session)
            raise _not_member()

        _apply_profile(user, claims)
        session.last_seen_at = utcnow()
        db.commit()
        return user
