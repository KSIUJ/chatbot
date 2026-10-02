"""Endpointy logowania przez Keycloak KSI.

Za nginxem sa pod /api/auth/* (nginx obcina /api), backend widzi /auth/*.

    GET  /auth/login     -> 303 do Keycloaka (state, nonce, PKCE S256)
    GET  /auth/callback  -> wymiana kodu, walidacja, sprawdzenie grupy,
                            ciasteczko sesji, 303 na frontend
    GET  /auth/me        -> dane zalogowanego czlonka albo 401/403/503
    POST /auth/logout    -> kasuje sesje, zwraca adres wylogowania z Keycloaka
"""

from __future__ import annotations

import hmac
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..llm.language import parse_language
from ..models import User
from ..response import LogoutResponse, UserResponse
from .crypto import DecryptionError, LoginState, TokenCipher
from .dependencies import get_oidc_client, get_token_cipher, require_member
from .oidc import OIDCClient, OIDCError, ProviderUnavailableError
from .service import (
    create_session,
    decrypt_id_token,
    delete_session,
    find_session,
    is_member,
    purge_expired_sessions,
    upsert_user,
)
from .settings import AuthSettings, get_auth_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_NO_STORE = {"Cache-Control": "no-store"}


def _set_cookie(response: RedirectResponse | JSONResponse, name: str, value: str, max_age: int, settings: AuthSettings) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        # Lax, nie Strict: callback przychodzi jako przekierowanie z auth.ksi.sh
        samesite="lax",
    )


def _clear_cookie(response: RedirectResponse | JSONResponse, name: str, settings: AuthSettings) -> None:
    response.delete_cookie(name, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")


def _frontend_url(settings: AuthSettings, auth_error: str | None = None) -> str:
    if auth_error is None:
        return settings.frontend_url
    parts = urlsplit(settings.frontend_url)
    query = [*parse_qsl(parts.query), ("auth_error", auth_error)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(query), parts.fragment))


def _fail(settings: AuthSettings, code: str) -> RedirectResponse:
    """Powrot na frontend z ?auth_error=<code>; ciasteczko logowania znika."""
    response = RedirectResponse(_frontend_url(settings, code), status_code=303, headers=_NO_STORE)
    _clear_cookie(response, settings.login_state_cookie_name, settings)
    return response


def _parse_prompt(value: str | None) -> str | None:
    """Jedyna przepuszczana wartosc OIDC prompt to "login" (logowanie innym
    kontem); reszta (none, consent, ...) jest pomijana."""
    return "login" if value == "login" else None


@router.get("/login")
def login(
    ui_locales: str | None = None,
    prompt: str | None = None,
    settings: AuthSettings = Depends(get_auth_settings),
    oidc: OIDCClient = Depends(get_oidc_client),
    cipher: TokenCipher = Depends(get_token_cipher),
) -> RedirectResponse:
    """Zaczyna logowanie: przekierowanie do Keycloaka, w jezyku interfejsu
    (ui_locales) - nieobslugiwana wartosc jest pomijana. prompt=login wymusza
    formularz logowania mimo sesji SSO (np. po odmowie dla konta spoza grupy)."""
    login_state = LoginState.generate()
    try:
        url = oidc.build_authorization_url(
            login_state.state,
            login_state.nonce,
            login_state.code_challenge,
            ui_locales=parse_language(ui_locales),
            prompt=_parse_prompt(prompt),
        )
    except ProviderUnavailableError as exc:
        logger.error("cannot start login: %s", exc)
        return _fail(settings, "provider_unavailable")

    response = RedirectResponse(url, status_code=303, headers=_NO_STORE)
    _set_cookie(
        response,
        settings.login_state_cookie_name,
        login_state.seal(cipher),
        settings.login_state_max_age_seconds,
        settings,
    )
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    settings: AuthSettings = Depends(get_auth_settings),
    oidc: OIDCClient = Depends(get_oidc_client),
    cipher: TokenCipher = Depends(get_token_cipher),
) -> RedirectResponse:
    """Powrot z Keycloaka. Sesja powstaje tylko dla czlonka wymaganej grupy."""
    if error is not None:
        logger.info("login returned error from identity provider: %s", error)
        return _fail(settings, "access_denied" if error == "access_denied" else "login_failed")

    sealed = request.cookies.get(settings.login_state_cookie_name)
    if not code or not state or not sealed:
        return _fail(settings, "invalid_state")
    try:
        login_state = LoginState.unseal(sealed, cipher, settings.login_state_max_age_seconds)
    except DecryptionError:
        return _fail(settings, "invalid_state")
    if not hmac.compare_digest(login_state.state, state):
        return _fail(settings, "invalid_state")

    try:
        tokens = oidc.exchange_code(code, login_state.code_verifier)
        if tokens.id_token is None:
            logger.warning("token response without id_token - is 'openid' in OIDC_SCOPES?")
            return _fail(settings, "login_failed")
        id_claims = oidc.validate_id_token(tokens.id_token, nonce=login_state.nonce)
        userinfo = oidc.userinfo(tokens.access_token)
    except ProviderUnavailableError as exc:
        logger.error("login failed, identity provider unavailable: %s", exc)
        return _fail(settings, "provider_unavailable")
    except OIDCError as exc:
        logger.warning("login failed: %s", exc)
        return _fail(settings, "login_failed")

    sub = id_claims.get("sub")
    if not isinstance(sub, str) or userinfo.get("sub") != sub:
        logger.warning("userinfo sub does not match ID token sub")
        return _fail(settings, "login_failed")
    if not is_member(userinfo, settings):
        groups = userinfo.get(settings.groups_claim)
        if groups is None:
            # najczestszy blad konfiguracji: wtedy nikt nie moze sie zalogowac
            logger.warning(
                "login refused: userinfo for %s has no %r claim - check the client's Group Membership "
                "mapper (claim name, Add to userinfo) or whether the user is in any group",
                sub,
                settings.groups_claim,
            )
        else:
            logger.info("login refused: %s is not in %s (groups: %s)", sub, settings.required_group, groups)
        return _fail(settings, "not_member")

    purge_expired_sessions(db)
    user = upsert_user(db, sub, {**id_claims, **userinfo})
    if not user.is_active:
        db.commit()
        logger.info("login refused: account %s is disabled locally", user.id)
        return _fail(settings, "login_failed")
    raw_token = create_session(db, user, tokens, cipher, settings)

    response = RedirectResponse(_frontend_url(settings), status_code=303, headers=_NO_STORE)
    _clear_cookie(response, settings.login_state_cookie_name, settings)
    _set_cookie(response, settings.session_cookie_name, raw_token, settings.session_max_age_seconds, settings)
    return response


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(require_member)) -> UserResponse:
    """Zalogowany czlonek KSI - frontend wola to przy starcie."""
    return UserResponse(id=user.id, email=user.email, username=user.username, name=user.name)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    settings: AuthSettings = Depends(get_auth_settings),
    oidc: OIDCClient = Depends(get_oidc_client),
    cipher: TokenCipher = Depends(get_token_cipher),
) -> JSONResponse:
    """Konczy sesje aplikacji. Zwraca adres, pod ktory frontend przekierowuje,
    zeby zakonczyc tez sesje w Keycloaku. Idempotentne."""
    id_token_hint: str | None = None
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        session = find_session(db, raw_token)
        if session is not None:
            id_token_hint = decrypt_id_token(session, cipher)
            delete_session(db, session)

    try:
        logout_url = oidc.build_logout_url(id_token_hint)
    except ProviderUnavailableError as exc:
        logger.warning("cannot build identity provider logout URL: %s", exc)
        logout_url = None

    response = JSONResponse(LogoutResponse(logout_url=logout_url).model_dump(), headers=_NO_STORE)
    _clear_cookie(response, settings.session_cookie_name, settings)
    return response
