"""Endpointy polaczenia konta z USOS (OAuth 1.0a, USOS API UJ).

Za nginxem sa pod /api/usos/* (nginx obcina /api), backend widzi /usos/*.
Wszystkie wymagaja zalogowanego czlonka KSI, zmieniajace stan - takze
dozwolonego naglowka Origin.

    GET    /usos/status    -> {available, connected, needs_reconnect, name,
                               connected_at, scopes} (bez tokenow)
    POST   /usos/connect   -> request token z USOS, zaszyfrowane ciasteczko
                              laczenia, {authorize_url} do strony zgody w USOS
    GET    /usos/callback  -> powrot z USOS: sprawdzenie ciasteczka (ta sama
                              przegladarka i to samo konto), wymiana na token
                              dostepu, zapis polaczenia, 303 na frontend
                              (?usos=connected albo ?usos_error=<kod>)
    DELETE /usos/link      -> cofniecie tokenu w USOS i usuniecie polaczenia

POST (nie GET) przy /connect: zwykly link albo obrazek z obcej strony nie
zacznie laczenia. Tokenow, verifierow ani podpisow nie logujemy.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth.crypto import DecryptionError, TokenCipher
from ..auth.dependencies import (
    auth_error,
    get_oidc_client,
    get_token_cipher,
    require_member,
    require_member_context,
    verify_origin,
)
from ..auth.oidc import OIDCClient
from ..auth.settings import AuthSettings, get_auth_settings
from ..database import get_db
from ..models import User
from .client import VERIFIER_PATTERN, UsosClient, UsosError, UsosUnauthorizedError
from .crypto import ConnectState, UserToken, UsosTokenCipher
from .dependencies import get_usos_client, get_usos_token_cipher, require_usos_available
from .schemas import UsosConnectResponse, UsosStatusResponse
from .service import as_utc, get_link, revoke_quietly, save_link, unlink
from .settings import UsosSettings, get_usos_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usos", tags=["usos"])

_NO_STORE = {"Cache-Control": "no-store"}
_USER_FIELDS = "id|first_name|last_name"
_USOS_ID_MAX = 32


def connect_cookie_name(auth: AuthSettings) -> str:
    """Prefiks __Host- (tylko przy Secure) blokuje nadpisanie ciasteczka
    z innej subdomeny ksi.sh - jak ciasteczka logowania."""
    return "__Host-chatbot_usos" if auth.cookie_secure else "chatbot_usos"


def _frontend_url(auth: AuthSettings, key: str, value: str) -> str:
    parts = urlsplit(auth.frontend_url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in ("usos", "usos_error")]
    query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(query), parts.fragment))


def _back(auth: AuthSettings, *, error: str | None = None) -> RedirectResponse:
    """Powrot na frontend; ciasteczko laczenia znika zawsze (jednorazowe)."""
    url = _frontend_url(auth, "usos_error", error) if error else _frontend_url(auth, "usos", "connected")
    response = RedirectResponse(url, status_code=303, headers=_NO_STORE)
    response.delete_cookie(
        connect_cookie_name(auth), path="/", httponly=True, secure=auth.cookie_secure, samesite="lax"
    )
    return response


def _same(a: str, b: str) -> bool:
    """Porownanie w stalym czasie; napisy spoza ASCII tez (bajty UTF-8)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _identity(info: Any) -> tuple[str, str | None] | None:
    """Id osoby w USOS i imie z nazwiskiem z services/users/user."""
    if not isinstance(info, dict):
        return None
    raw_id = info.get("id")
    if isinstance(raw_id, int) and not isinstance(raw_id, bool):
        raw_id = str(raw_id)
    if not isinstance(raw_id, str) or not raw_id.strip() or len(raw_id) > _USOS_ID_MAX:
        return None
    names = [info.get(key) for key in ("first_name", "last_name")]
    name = " ".join(part.strip() for part in names if isinstance(part, str) and part.strip())
    return raw_id.strip(), name or None


@router.get("/status", response_model=UsosStatusResponse)
def status(
    user: User = Depends(require_member),
    settings: UsosSettings = Depends(get_usos_settings),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Stan polaczenia zalogowanego czlonka. Dziala tez przy wylaczonej
    funkcji - istniejace polaczenie mozna wtedy nadal usunac."""
    link = get_link(db, user.id)
    body = UsosStatusResponse(
        available=settings.available,
        connected=link is not None and link.needs_reconnect_at is None,
        needs_reconnect=link is not None and link.needs_reconnect_at is not None,
        name=link.usos_name if link is not None else None,
        connected_at=as_utc(link.created_at) if link is not None else None,
        scopes=[s for s in link.scopes.split("|") if s] if link is not None else [],
    )
    return JSONResponse(body.model_dump(mode="json"), headers=_NO_STORE)


@router.post("/connect", response_model=UsosConnectResponse, dependencies=[Depends(verify_origin)])
def connect(
    user: User = Depends(require_member),
    settings: UsosSettings = Depends(require_usos_available),
    auth: AuthSettings = Depends(get_auth_settings),
    cipher: TokenCipher = Depends(get_token_cipher),
    client: UsosClient = Depends(get_usos_client),
) -> JSONResponse:
    """Zaczyna laczenie: request token z USOS (z adresem powrotu i
    uprawnieniami), zaszyfrowany w ciasteczku razem z id konta.

    Raises:
        HTTPException: 503 usos_unavailable (funkcja wylaczona), 502 usos_failed
            (USOS nie wydal request tokenu).
    """
    try:
        request_token, request_secret = client.request_token()
    except UsosError as exc:
        logger.warning("usos request_token failed for user %s: %s", user.id, type(exc).__name__)
        raise auth_error(502, "usos_failed", "USOS nie odpowiada. Sprobuj za chwile.") from None

    state = ConnectState.new(request_token, request_secret, user.id, settings.scopes)
    body = UsosConnectResponse(authorize_url=client.authorize_url(request_token))
    response = JSONResponse(body.model_dump(), headers=_NO_STORE)
    response.set_cookie(
        connect_cookie_name(auth),
        state.seal(cipher),
        max_age=settings.connect_state_max_age_seconds,
        path="/",
        httponly=True,
        secure=auth.cookie_secure,
        # Lax, nie Strict: callback przychodzi jako przekierowanie z apps.usos.uj.edu.pl
        samesite="lax",
    )
    return response


@router.get("/callback")
def callback(
    request: Request,
    oauth_token: str | None = None,
    oauth_verifier: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthSettings = Depends(get_auth_settings),
    oidc: OIDCClient = Depends(get_oidc_client),
    cipher: TokenCipher = Depends(get_token_cipher),
    settings: UsosSettings = Depends(get_usos_settings),
    client: UsosClient = Depends(get_usos_client),
    token_cipher: UsosTokenCipher = Depends(get_usos_token_cipher),
) -> RedirectResponse:
    """Powrot z USOS. Polaczenie powstaje tylko dla konta, ktore zaczelo
    laczenie, w tej samej przegladarce i przed uplywem 10 minut. Kody bledow:
    unavailable, session, denied, expired, mismatch, failed."""
    if not settings.available:
        return _back(auth, error="unavailable")
    # Sesja jak w require_member, ale bez JSON-owego 401 - to nawigacja przegladarki
    try:
        user = require_member_context(request, db, auth, oidc, cipher).user
    except HTTPException:
        return _back(auth, error="session")

    if not oauth_verifier:
        # odmowa w USOS: powrot bez verifiera
        logger.info("usos connect cancelled by user %s", user.id)
        return _back(auth, error="denied")
    sealed = request.cookies.get(connect_cookie_name(auth))
    if not sealed:
        return _back(auth, error="expired")
    try:
        state = ConnectState.unseal(sealed, cipher, settings.connect_state_max_age_seconds)
    except DecryptionError:
        return _back(auth, error="expired")
    if not oauth_token or not _same(oauth_token, state.request_token):
        logger.warning("usos callback with a request token not issued to this browser (user %s)", user.id)
        return _back(auth, error="mismatch")
    if not _same(state.user_id, user.id):
        logger.warning("usos callback for another account than the one that started it (user %s)", user.id)
        return _back(auth, error="mismatch")
    if not VERIFIER_PATTERN.fullmatch(oauth_verifier):
        return _back(auth, error="failed")

    try:
        token, secret = client.access_token(state.request_token, state.request_secret, oauth_verifier)
    except UsosUnauthorizedError:
        return _back(auth, error="expired")
    except UsosError as exc:
        logger.warning("usos access_token failed for user %s: %s", user.id, type(exc).__name__)
        return _back(auth, error="failed")

    user_token = UserToken(user_id=user.id, token=token, secret=secret)
    try:
        identity = _identity(client.call(user_token, "services/users/user", fields=_USER_FIELDS))
    except UsosError as exc:
        logger.warning("usos users/user failed for user %s: %s", user.id, type(exc).__name__)
        identity = None
    if identity is None:
        revoke_quietly(client, user_token)
        return _back(auth, error="failed")

    usos_user_id, usos_name = identity
    _, previous = save_link(
        db,
        token_cipher,
        user_id=user.id,
        token=token,
        secret=secret,
        usos_user_id=usos_user_id,
        usos_name=usos_name,
        scopes=state.scopes,
    )
    if previous is not None:
        revoke_quietly(client, previous)
    logger.info("user %s connected usos account", user.id)
    return _back(auth)


@router.delete("/link", status_code=204, dependencies=[Depends(verify_origin)])
def delete_link(
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
    settings: UsosSettings = Depends(get_usos_settings),
    client: UsosClient = Depends(get_usos_client),
    token_cipher: UsosTokenCipher = Depends(get_usos_token_cipher),
) -> Response:
    """Rozlacza konto: cofa token w USOS (najlepiej jak sie da - blad tylko
    w logu) i usuwa polaczenie. Dziala tez przy wylaczonej funkcji; bez klucza
    aplikacji tylko usuwa wiersz. Idempotentne."""
    can_sign = bool(settings.consumer_key and settings.consumer_secret)
    if unlink(db, token_cipher, client if can_sign else None, user.id):
        logger.info("user %s disconnected usos account", user.id)
    return Response(status_code=204, headers=_NO_STORE)
