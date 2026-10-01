"""Konfiguracja logowania OIDC (Keycloak KSI) czytana ze zmiennych srodowiskowych.

Wszystko, co zalezy od srodowiska (adres Keycloaka, klient, adresy powrotu,
wymagana grupa, grupa adminow), jest w env - opis kazdej zmiennej w .env.example. Brak
wymaganej zmiennej zatrzymuje start backendu z lista brakow, zamiast wywalac
sie dopiero przy pierwszym logowaniu.
"""

from __future__ import annotations

import math
import os
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

from ..config import DEFAULT_FRONTEND_ORIGINS, parse_origins

# Tylko algorytmy asymetryczne - HS* (klucz wspoldzielony) i "none" nigdy nie
# moga podpisac tokenu, ktoremu ufamy. Keycloak KSI podpisuje obecnie ES256.
DEFAULT_ID_TOKEN_ALGORITHMS: tuple[str, ...] = (
    "RS256", "RS384", "RS512",
    "PS256", "PS384", "PS512",
    "ES256", "ES384", "ES512",
    "EdDSA",
)
_FORBIDDEN_ALGORITHMS = frozenset({"none", "HS256", "HS384", "HS512"})

MIN_SECRET_KEY_LENGTH = 32
# Czas na dokonczenie logowania w Keycloaku (ciasteczko ze state, nonce i PKCE)
LOGIN_STATE_MAX_AGE_SECONDS = 600
_TRUE = frozenset({"1", "true", "yes", "on", "tak"})
_FALSE = frozenset({"0", "false", "no", "off", "nie"})
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

DEFAULT_REQUIRED_GROUP = "/Członek"
# Zarzad KSI przeglada oceny i zgloszenia odpowiedzi (/admin/*)
DEFAULT_ADMIN_GROUP = "/Zarząd"


class AuthConfigError(RuntimeError):
    """Konfiguracja logowania w env jest niekompletna albo bledna."""


@dataclass(frozen=True)
class AuthSettings:
    """Zwalidowana konfiguracja logowania OIDC."""

    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    post_logout_redirect_uri: str
    scopes: str
    required_group: str
    # None = nikt nie jest adminem (OIDC_ADMIN_GROUP=off)
    admin_group: str | None
    groups_claim: str
    id_token_algorithms: tuple[str, ...]
    secret_key: str
    frontend_url: str
    cookie_secure: bool
    session_max_age_seconds: int
    login_state_max_age_seconds: int
    http_timeout_seconds: float
    allowed_origins: tuple[str, ...]

    @property
    def session_cookie_name(self) -> str:
        """Prefiks __Host- (tylko przy Secure) blokuje nadpisanie ciasteczka
        z innej subdomeny ksi.sh."""
        return "__Host-chatbot_session" if self.cookie_secure else "chatbot_session"

    @property
    def login_state_cookie_name(self) -> str:
        return "__Host-chatbot_login" if self.cookie_secure else "chatbot_login"

    @property
    def discovery_url(self) -> str:
        return self.issuer.rstrip("/") + "/.well-known/openid-configuration"


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _is_absolute_http_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _is_https_or_local(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS)


def load_auth_settings(env: Mapping[str, str]) -> AuthSettings:
    """Buduje AuthSettings z mapy zmiennych srodowiskowych.

    Args:
        env: zrodlo zmiennych, zwykle os.environ (w testach zwykly dict).

    Returns:
        Zwalidowana konfiguracja.

    Raises:
        AuthConfigError: z lista wszystkich problemow naraz, zeby nie trzeba
            bylo poprawiac .env po jednej zmiennej.
    """
    errors: list[str] = []

    def get(name: str, default: str = "") -> str:
        return (env.get(name) or default).strip()

    def required(name: str) -> str:
        value = get(name)
        if not value:
            errors.append(f"{name} jest wymagane")
        return value

    def as_int(name: str, default: int) -> int:
        raw = get(name)
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            errors.append(f"{name} musi byc liczba calkowita, jest {raw!r}")
            return default
        if value <= 0:
            errors.append(f"{name} musi byc dodatnie")
        return value

    def as_float(name: str, default: float) -> float:
        raw = get(name)
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            value = math.nan
        if not math.isfinite(value):
            errors.append(f"{name} musi byc liczba, jest {raw!r}")
            return default
        if value <= 0:
            errors.append(f"{name} musi byc dodatnie")
        return value

    issuer = required("OIDC_ISSUER").rstrip("/")
    client_id = required("OIDC_CLIENT_ID")
    client_secret = required("OIDC_CLIENT_SECRET")
    redirect_uri = required("OIDC_REDIRECT_URI")
    secret_key = required("AUTH_SECRET_KEY")

    if issuer and not _is_https_or_local(issuer):
        errors.append("OIDC_ISSUER musi byc adresem https:// (http tylko dla localhost)")
    if redirect_uri and not _is_absolute_http_url(redirect_uri):
        errors.append("OIDC_REDIRECT_URI musi byc pelnym adresem http(s)://.../api/auth/callback")
    if secret_key and len(secret_key) < MIN_SECRET_KEY_LENGTH:
        errors.append(f"AUTH_SECRET_KEY musi miec co najmniej {MIN_SECRET_KEY_LENGTH} znaki")

    public_origin = _origin_of(redirect_uri) if redirect_uri and _is_absolute_http_url(redirect_uri) else ""

    post_logout_redirect_uri = get("OIDC_POST_LOGOUT_REDIRECT_URI") or (public_origin + "/" if public_origin else "")
    if post_logout_redirect_uri and not _is_absolute_http_url(post_logout_redirect_uri):
        errors.append("OIDC_POST_LOGOUT_REDIRECT_URI musi byc pelnym adresem http(s)://")

    scopes = " ".join(get("OIDC_SCOPES", "openid profile email").split())
    if "openid" not in scopes.split():
        errors.append("OIDC_SCOPES musi zawierac 'openid'")

    # NFC: "ł" wpisane w .env i przyslane przez Keycloaka musza sie porownac rowno
    required_group = unicodedata.normalize("NFC", get("OIDC_REQUIRED_GROUP", DEFAULT_REQUIRED_GROUP))
    if not required_group:
        errors.append("OIDC_REQUIRED_GROUP nie moze byc puste")
    # puste = domyslna grupa (jak kazda zmienna w .env.example), off/false/0/no/nie = brak adminow
    admin_group_raw = unicodedata.normalize("NFC", get("OIDC_ADMIN_GROUP") or DEFAULT_ADMIN_GROUP)
    admin_group = None if admin_group_raw.lower() in _FALSE else admin_group_raw
    groups_claim = get("OIDC_GROUPS_CLAIM", "groups")

    algorithms_raw = get("OIDC_ID_TOKEN_ALGORITHMS")
    algorithms = (
        tuple(a.strip() for a in algorithms_raw.split(",") if a.strip())
        if algorithms_raw
        else DEFAULT_ID_TOKEN_ALGORITHMS
    )
    forbidden = sorted(set(algorithms) & _FORBIDDEN_ALGORITHMS)
    if forbidden:
        errors.append(f"OIDC_ID_TOKEN_ALGORITHMS nie moze zawierac {', '.join(forbidden)}")

    # Po logowaniu backend przekierowuje tutaj. "/" dziala wszedzie tam, gdzie
    # frontend i /api sa na jednym originie (Docker/nginx, vite z proxy).
    frontend_url = get("AUTH_FRONTEND_URL", "/")
    if not (frontend_url.startswith("/") and not frontend_url.startswith("//")) and not _is_absolute_http_url(frontend_url):
        errors.append("AUTH_FRONTEND_URL musi byc sciezka (np. /) albo pelnym adresem http(s)://")

    cookie_secure_raw = get("AUTH_COOKIE_SECURE").lower()
    if not cookie_secure_raw:
        cookie_secure = redirect_uri.startswith("https://")
    elif cookie_secure_raw in _TRUE:
        cookie_secure = True
    elif cookie_secure_raw in _FALSE:
        cookie_secure = False
    else:
        errors.append("AUTH_COOKIE_SECURE musi byc true/false")
        cookie_secure = True

    session_max_age_hours = as_int("AUTH_SESSION_MAX_AGE_HOURS", 24 * 7)
    http_timeout = as_float("OIDC_HTTP_TIMEOUT", 10.0)

    frontend_origins = parse_origins(get("FRONTEND_ORIGINS", DEFAULT_FRONTEND_ORIGINS))
    allowed_origins = tuple(dict.fromkeys([o for o in [public_origin, *frontend_origins] if o]))

    if errors:
        raise AuthConfigError(
            "Bledna konfiguracja logowania OIDC (patrz .env.example):\n- " + "\n- ".join(errors)
        )

    return AuthSettings(
        issuer=issuer,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        post_logout_redirect_uri=post_logout_redirect_uri,
        scopes=scopes,
        required_group=required_group,
        admin_group=admin_group,
        groups_claim=groups_claim,
        id_token_algorithms=algorithms,
        secret_key=secret_key,
        frontend_url=frontend_url,
        cookie_secure=cookie_secure,
        session_max_age_seconds=session_max_age_hours * 3600,
        login_state_max_age_seconds=LOGIN_STATE_MAX_AGE_SECONDS,
        http_timeout_seconds=http_timeout,
        allowed_origins=allowed_origins,
    )


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    """Konfiguracja z os.environ, liczona raz na proces. Dependency FastAPI -
    testy podmieniaja ja przez app.dependency_overrides."""
    return load_auth_settings(os.environ)
