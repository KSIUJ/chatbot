"""Klient OIDC (Authorization Code + PKCE) dla Keycloaka KSI.

Backend jest klientem poufnym (BFF): sam wymienia kod na tokeny, sam je
odswieza i sam pyta userinfo. Przegladarka nigdy nie widzi tokenow Keycloaka.

Tylko synchroniczny httpx - endpointy FastAPI w tym projekcie sa synchroniczne
(uruchamiane w threadpoolu), wiec blokujace wywolania HTTP sa tu w porzadku.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import GuestProtocol, KeySet

from .settings import AuthSettings

logger = logging.getLogger(__name__)

# Tolerancja rozjechanych zegarow miedzy nami a Keycloakiem.
CLOCK_LEEWAY_SECONDS = 60
# Nie pobieraj JWKS czesciej niz co tyle sekund (nieznany kid moze byc atakiem).
JWKS_MIN_REFRESH_INTERVAL_SECONDS = 60

JSONObject = dict[str, object]


class OIDCError(Exception):
    """Bazowy blad komunikacji z dostawca tozsamosci."""


class ProviderUnavailableError(OIDCError):
    """Keycloak nie odpowiada, zwraca 5xx albo odpowiedz nie do sparsowania.
    Nie mowi nic o uzytkowniku - aplikacja odpowiada 503 i niczego nie kasuje."""


class InvalidGrantError(OIDCError):
    """Kod autoryzacyjny albo refresh token jest niewazny (np. sesja w Keycloaku
    wygasla, admin wylogowal uzytkownika albo zablokowal konto)."""


class UserinfoUnauthorizedError(OIDCError):
    """Userinfo odrzucilo access token (401/403)."""


class IDTokenValidationError(OIDCError):
    """ID token nie przeszedl walidacji (podpis, iss, aud, exp, nonce...)."""


@dataclass(frozen=True)
class ProviderMetadata:
    """Potrzebne pola z /.well-known/openid-configuration."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    jwks_uri: str
    end_session_endpoint: str | None


@dataclass(frozen=True)
class TokenSet:
    """Odpowiedz token endpointu."""

    access_token: str
    access_token_expires_at: datetime
    refresh_token: str | None
    id_token: str | None


def _require_str(data: JSONObject, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ProviderUnavailableError(f"provider response is missing {key!r}")
    return value


def _optional_str(data: JSONObject, key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


class OIDCClient:
    """Klient jednego dostawcy OIDC. Bezpieczny watkowo; jedna instancja na proces."""

    def __init__(
        self,
        settings: AuthSettings,
        http: httpx.Client,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._http = http
        self._clock = clock
        self._lock = threading.Lock()
        self._metadata: ProviderMetadata | None = None
        self._jwks: KeySet | None = None
        self._jwks_fetched_at = 0.0

    # --- HTTP -----------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return self._http.request(method, url, data=data, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("OIDC request %s %s failed: %s", method, url, exc)
            raise ProviderUnavailableError(f"cannot reach identity provider: {exc}") from exc

    @staticmethod
    def _json(response: httpx.Response) -> JSONObject:
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("identity provider returned non-JSON response") from exc
        if not isinstance(data, dict):
            raise ProviderUnavailableError("identity provider returned unexpected JSON")
        return data

    # --- metadane i klucze ------------------------------------------------

    def metadata(self) -> ProviderMetadata:
        """Metadane dostawcy (pobierane raz, potem z pamieci)."""
        with self._lock:
            if self._metadata is not None:
                return self._metadata

        response = self._request("GET", self._settings.discovery_url)
        if response.status_code != 200:
            raise ProviderUnavailableError(f"discovery returned HTTP {response.status_code}")
        data = self._json(response)

        issuer = _require_str(data, "issuer").rstrip("/")
        if issuer != self._settings.issuer:
            # Zle OIDC_ISSUER w env albo podstawiony dokument - nie ufamy mu.
            raise ProviderUnavailableError(
                f"discovery issuer {issuer!r} does not match OIDC_ISSUER {self._settings.issuer!r}"
            )
        metadata = ProviderMetadata(
            issuer=issuer,
            authorization_endpoint=_require_str(data, "authorization_endpoint"),
            token_endpoint=_require_str(data, "token_endpoint"),
            userinfo_endpoint=_require_str(data, "userinfo_endpoint"),
            jwks_uri=_require_str(data, "jwks_uri"),
            end_session_endpoint=_optional_str(data, "end_session_endpoint"),
        )
        with self._lock:
            self._metadata = metadata
        return metadata

    def _fetch_jwks(self) -> KeySet:
        response = self._request("GET", self.metadata().jwks_uri)
        if response.status_code != 200:
            raise ProviderUnavailableError(f"JWKS returned HTTP {response.status_code}")
        try:
            key_set = KeySet.import_key_set(self._json(response))  # type: ignore[arg-type]
        except (JoseError, ValueError, TypeError) as exc:
            raise ProviderUnavailableError("cannot parse JWKS") from exc
        with self._lock:
            self._jwks = key_set
            self._jwks_fetched_at = self._clock()
        return key_set

    @staticmethod
    def _has_kid(key_set: KeySet, kid: str) -> bool:
        try:
            key_set.get_by_kid(kid)
        except InvalidKeyIdError:
            return False
        return True

    def _key_for(self, kid: str) -> KeySet:
        """Zwraca KeySet zawierajacy klucz `kid`. Przy nieznanym kid pobiera JWKS
        ponownie (rotacja kluczy w Keycloaku), ale nie czesciej niz co
        JWKS_MIN_REFRESH_INTERVAL_SECONDS."""
        with self._lock:
            key_set = self._jwks
            fetched_at = self._jwks_fetched_at

        just_fetched = key_set is None
        if key_set is None:
            key_set = self._fetch_jwks()
        if self._has_kid(key_set, kid):
            return key_set
        if just_fetched or self._clock() - fetched_at < JWKS_MIN_REFRESH_INTERVAL_SECONDS:
            raise IDTokenValidationError(f"unknown signing key {kid!r}")

        key_set = self._fetch_jwks()
        if self._has_kid(key_set, kid):
            return key_set
        raise IDTokenValidationError(f"unknown signing key {kid!r}")

    # --- przeplyw logowania -----------------------------------------------

    def build_authorization_url(
        self, state: str, nonce: str, code_challenge: str, ui_locales: str | None = None
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self._settings.client_id,
            "redirect_uri": self._settings.redirect_uri,
            "scope": self._settings.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if ui_locales:
            # jezyk strony logowania Keycloaka (standardowy parametr OIDC)
            params["ui_locales"] = ui_locales
        return f"{self.metadata().authorization_endpoint}?{urlencode(params)}"

    def _token_request(self, form: dict[str, str]) -> TokenSet:
        form = {**form, "client_id": self._settings.client_id, "client_secret": self._settings.client_secret}
        requested_at = datetime.now(timezone.utc)
        response = self._request(
            "POST",
            self.metadata().token_endpoint,
            data=form,
            headers={"Accept": "application/json"},
        )
        if response.status_code in (400, 401):
            error = ""
            try:
                error = str(self._json(response).get("error", ""))
            except ProviderUnavailableError:
                pass
            if error == "invalid_grant":
                raise InvalidGrantError("authorization code or refresh token is no longer valid")
            # invalid_client / unauthorized_client itp. = zla konfiguracja klienta
            logger.error("OIDC token endpoint rejected the client: HTTP %s %s", response.status_code, error)
            raise ProviderUnavailableError(f"token endpoint rejected the request: {error or response.status_code}")
        if response.status_code != 200:
            raise ProviderUnavailableError(f"token endpoint returned HTTP {response.status_code}")

        data = self._json(response)
        expires_in = data.get("expires_in")
        lifetime = int(expires_in) if isinstance(expires_in, (int, float)) and expires_in > 0 else 60
        return TokenSet(
            access_token=_require_str(data, "access_token"),
            access_token_expires_at=requested_at + timedelta(seconds=lifetime),
            refresh_token=_optional_str(data, "refresh_token"),
            id_token=_optional_str(data, "id_token"),
        )

    def exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        """Wymienia kod z callbacku na tokeny.

        Raises:
            InvalidGrantError: kod niewazny/zuzyty.
            ProviderUnavailableError: problem z Keycloakiem lub konfiguracja klienta.
        """
        return self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._settings.redirect_uri,
            "code_verifier": code_verifier,
        })

    def refresh(self, refresh_token: str) -> TokenSet:
        """Odswieza tokeny.

        Raises:
            InvalidGrantError: sesja w Keycloaku juz nie istnieje.
            ProviderUnavailableError: problem z Keycloakiem.
        """
        return self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def userinfo(self, access_token: str) -> JSONObject:
        """Aktualne dane uzytkownika - Keycloak liczy je przy kazdym wywolaniu,
        wiec zmiana grup jest widoczna od razu.

        Raises:
            UserinfoUnauthorizedError: token odrzucony (wygasl, sesja zakonczona).
            ProviderUnavailableError: problem z Keycloakiem.
        """
        response = self._request(
            "GET",
            self.metadata().userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if response.status_code in (401, 403):
            raise UserinfoUnauthorizedError(f"userinfo returned HTTP {response.status_code}")
        if response.status_code != 200:
            raise ProviderUnavailableError(f"userinfo returned HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            # Podpisane userinfo (application/jwt) nie jest obslugiwane - klient
            # w Keycloaku musi miec "User info signed response algorithm" = unsigned.
            raise ProviderUnavailableError(f"unsupported userinfo content type {content_type!r}")
        data = self._json(response)
        _require_str(data, "sub")
        return data

    def validate_id_token(self, id_token: str, nonce: str) -> JSONObject:
        """Weryfikuje podpis (JWKS, tylko algorytmy asymetryczne) i claimy
        iss, aud, azp, exp, iat, sub, nonce.

        Raises:
            IDTokenValidationError: token niepoprawny.
            ProviderUnavailableError: nie da sie pobrac kluczy.
        """
        def resolve_key(obj: GuestProtocol) -> KeySet:
            kid = obj.headers().get("kid")
            if not isinstance(kid, str) or not kid:
                raise IDTokenValidationError("ID token has no kid header")
            return self._key_for(kid)

        try:
            token = jwt.decode(id_token, resolve_key, algorithms=list(self._settings.id_token_algorithms))
            registry = jwt.JWTClaimsRegistry(
                now=int(self._clock()),
                leeway=CLOCK_LEEWAY_SECONDS,
                iss={"essential": True, "value": self._settings.issuer},
                aud={"essential": True, "value": self._settings.client_id},
                sub={"essential": True},
                exp={"essential": True},
                iat={"essential": True},
                nonce={"essential": True, "value": nonce},
            )
            registry.validate(token.claims)
        except JoseError as exc:
            raise IDTokenValidationError(f"invalid ID token: {exc}") from exc

        claims: JSONObject = dict(token.claims)
        audience = claims.get("aud")
        azp = claims.get("azp")
        if isinstance(audience, list) and len(audience) > 1 and azp != self._settings.client_id:
            raise IDTokenValidationError("ID token azp does not match client_id")
        if azp is not None and azp != self._settings.client_id:
            raise IDTokenValidationError("ID token azp does not match client_id")
        return claims

    def build_logout_url(self, id_token_hint: str | None) -> str | None:
        """Adres wylogowania z Keycloaka (RP-initiated logout) albo None, gdy
        dostawca go nie oglasza."""
        endpoint = self.metadata().end_session_endpoint
        if endpoint is None:
            return None
        params = {
            "client_id": self._settings.client_id,
            "post_logout_redirect_uri": self._settings.post_logout_redirect_uri,
        }
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{endpoint}?{urlencode(params)}"
