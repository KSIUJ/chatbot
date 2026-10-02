"""Zaleznosci FastAPI dla logowania: klient OIDC, szyfrowanie, biezacy uzytkownik
(czlonek, admin) i sprawdzanie naglowka Origin."""

from __future__ import annotations

import logging
from functools import lru_cache

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from .crypto import TokenCipher
from .oidc import OIDCClient, ProviderUnavailableError
from .service import AuthenticatedMember, AuthFailure, authenticate
from .settings import AuthSettings, get_auth_settings

logger = logging.getLogger(__name__)

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def auth_error(status_code: int, code: str, message: str) -> HTTPException:
    """HTTPException z detail = {"code", "message"} - frontend rozpoznaje po code."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@lru_cache(maxsize=4)
def _cipher_for(settings: AuthSettings) -> TokenCipher:
    return TokenCipher(settings.secret_key)


@lru_cache(maxsize=4)
def _oidc_client_for(settings: AuthSettings) -> OIDCClient:
    http = httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=False)
    return OIDCClient(settings, http)


def get_token_cipher(settings: AuthSettings = Depends(get_auth_settings)) -> TokenCipher:
    return _cipher_for(settings)


def get_oidc_client(settings: AuthSettings = Depends(get_auth_settings)) -> OIDCClient:
    return _oidc_client_for(settings)


def require_member_context(
    request: Request,
    db: Session = Depends(get_db),
    settings: AuthSettings = Depends(get_auth_settings),
    oidc: OIDCClient = Depends(get_oidc_client),
    cipher: TokenCipher = Depends(get_token_cipher),
) -> AuthenticatedMember:
    """Zalogowany uzytkownik, ktory w tej chwili jest w wymaganej grupie,
    razem z flaga admina. FastAPI liczy to raz na zapytanie, nawet gdy endpoint
    potrzebuje i require_member, i require_admin.

    Raises:
        HTTPException: 401 (brak/wygasla sesja), 403 (brak w grupie),
            503 (Keycloak niedostepny - nie da sie potwierdzic czlonkostwa).
    """
    raw_token = request.cookies.get(settings.session_cookie_name)
    try:
        return authenticate(db, raw_token, oidc, cipher, settings)
    except AuthFailure as failure:
        raise auth_error(failure.status_code, failure.code, failure.message) from None
    except ProviderUnavailableError as exc:
        logger.error("cannot verify session with identity provider: %s", exc)
        raise auth_error(
            503, "provider_unavailable", "Serwer logowania KSI jest niedostepny. Sprobuj za chwile."
        ) from None


def require_member(member: AuthenticatedMember = Depends(require_member_context)) -> User:
    """Zalogowany czlonek KSI (patrz require_member_context)."""
    return member.user


def require_admin(member: AuthenticatedMember = Depends(require_member_context)) -> User:
    """Czlonek KSI, ktory jest tez w grupie adminow (OIDC_ADMIN_GROUP).

    Raises:
        HTTPException: jak require_member_context, a do tego 403 "not_admin".
    """
    if not member.is_admin:
        logger.info("admin access refused for user %s", member.user.id)
        raise auth_error(403, "not_admin", "Dostep tylko dla zarzadu KSI.")
    return member.user


def verify_origin(request: Request, settings: AuthSettings = Depends(get_auth_settings)) -> None:
    """Odrzuca zapytania zmieniajace stan wyslane z obcego originu.

    SameSite=Lax nie chroni przed innymi subdomenami ksi.sh (to ta sama
    "site"), wiec sprawdzamy Origin wprost. Brak naglowka (curl, testy) jest
    dozwolony - taki klient i tak nie ma ciasteczka ofiary.
    """
    if request.method not in UNSAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin.rstrip("/") not in settings.allowed_origins:
        logger.warning("rejected %s %s from origin %s", request.method, request.url.path, origin)
        raise auth_error(403, "forbidden_origin", "Zapytanie z niedozwolonego originu.")
