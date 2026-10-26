"""Klient USOS API UJ dla polaczonych kont (OAuth 1.0a, podpis HMAC-SHA1).

Podpisy liczy oauthlib (RFC 5849, czysty Python) - ta sama biblioteka, ktorej
uzywa requests_oauthlib w scraperze, ale bez requests: transport to httpx,
jak w logowaniu OIDC (w testach httpx.MockTransport). Backend nie importuje
nic z pipeline/ (nie ma go w obrazie Dockera).

Wszystkie podpisane wywolania ida POST-em z parametrami w ciele formularza:
parametry nie trafiaja do adresow URL (ani do logow dostepu po drodze), a
token i podpis sa tylko w naglowku Authorization. Zadnej z tych wartosci nie
logujemy; bledy niosa najwyzej status HTTP i kod bledu USOS.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode

import httpx
from oauthlib.oauth1 import Client as OAuth1Client

from .crypto import UserToken
from .settings import UsosSettings

logger = logging.getLogger(__name__)

# oauthlib loguje na DEBUG podpisywany napis i podpis, httpx/httpcore na
# INFO/DEBUG adresy i naglowki - nic z tego nie moze trafic do logow.
for _name in ("oauthlib", "requests_oauthlib", "httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

USER_AGENT = "KSI-chatbot/1.0 (+https://chat.ksi.sh; usos-connect)"
_FORM = "application/x-www-form-urlencoded"
# tokeny USOS to znaki alfanumeryczne (jak w pipeline/scrapers/usos/login.py)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]{8,128}")
# oauth_verifier z callbacku USOS (PIN) - tez alfanumeryczny
VERIFIER_PATTERN = re.compile(r"[A-Za-z0-9]{1,128}")
_METHOD = re.compile(r"services/[a-z0-9_]+(?:/[a-z0-9_]+)+")
# tresc komunikatu USOS w wyjatku - dosc do diagnozy, bez zalewania logow
_MESSAGE_LIMIT = 300


class UsosError(Exception):
    """Wywolanie USOS API sie nie udalo."""


class UsosUnavailableError(UsosError):
    """USOS nie odpowiada: timeout, blad sieci, 429 albo 5xx."""


class UsosUnauthorizedError(UsosError):
    """USOS odrzucil token albo podpis (HTTP 401) - np. token cofniety przez
    uzytkownika w USOS albo wygasly request token przy laczeniu."""


class UsosApiError(UsosError):
    """Inny blad USOS API (4xx z JSON-em {message, error, reason}). `code` to
    pole "error" USOS (np. method_forbidden), `reason` - pole "reason"
    (np. scope_missing)."""

    def __init__(self, status: int, code: str | None, message: str, reason: str | None = None) -> None:
        super().__init__(f"HTTP {status} {code or '-'}: {message}")
        self.status = status
        self.code = code
        self.reason = reason
        self.message = message


def _param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set, frozenset)):
        return "|".join(str(item) for item in value)
    return str(value)


def _form_params(params: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Parametry metody: None pomijane, listy laczone "|", bool jako true/false."""
    return [(key, _param_value(value)) for key, value in params.items() if value is not None]


def _token_pair(response: httpx.Response) -> tuple[str, str]:
    """oauth_token i oauth_token_secret z odpowiedzi formularzowej OAuth
    (nadmiarowe pola sa pomijane, jak kaze dokumentacja USOS)."""
    form = dict(parse_qsl(response.text, keep_blank_values=True))
    token, secret = form.get("oauth_token", ""), form.get("oauth_token_secret", "")
    if not TOKEN_PATTERN.fullmatch(token) or not TOKEN_PATTERN.fullmatch(secret):
        raise UsosApiError(response.status_code, "invalid_token_response", "unexpected OAuth token response")
    return token, secret


def _raise_for_status(method: str, response: httpx.Response) -> None:
    status = response.status_code
    if 200 <= status < 300:
        return
    if status == 401:
        raise UsosUnauthorizedError(f"{method}: HTTP 401")
    if status == 429 or status >= 500:
        raise UsosUnavailableError(f"{method}: HTTP {status}")
    code: str | None = None
    reason: str | None = None
    message = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        code = body.get("error") if isinstance(body.get("error"), str) else None
        reason = body.get("reason") if isinstance(body.get("reason"), str) else None
        if isinstance(body.get("message"), str):
            message = body["message"][:_MESSAGE_LIMIT]
    if 300 <= status < 400:
        code = code or "redirect"
    raise UsosApiError(status, code, message or f"{method}: HTTP {status}", reason)


class UsosClient:
    """Wywolania USOS API podpisane kluczem aplikacji (i tokenem uzytkownika)."""

    def __init__(self, settings: UsosSettings, http: httpx.Client) -> None:
        self._settings = settings
        self._http = http
        self._base_url = settings.base_url.rstrip("/") + "/"

    def _url(self, method: str) -> str:
        if not _METHOD.fullmatch(method):
            raise ValueError(f"invalid USOS API method name: {method!r}")
        return self._base_url + method

    def _post(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        token: str | None = None,
        secret: str | None = None,
        verifier: str | None = None,
        callback: str | None = None,
    ) -> httpx.Response:
        url = self._url(method)
        signer = OAuth1Client(
            self._settings.consumer_key,
            client_secret=self._settings.consumer_secret,
            resource_owner_key=token,
            resource_owner_secret=secret,
            verifier=verifier,
            callback_uri=callback,
        )
        form = _form_params(params or {})
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if form:
            headers["Content-Type"] = _FORM
            _, signed_headers, body = signer.sign(url, http_method="POST", body=urlencode(form), headers=headers)
        else:
            _, signed_headers, body = signer.sign(url, http_method="POST", headers=headers)
        try:
            response = self._http.post(url, headers=signed_headers, content=body or b"")
        except httpx.TimeoutException:
            raise UsosUnavailableError(f"{method}: timeout") from None
        except httpx.HTTPError as exc:
            # bez str(exc) - i tak bez sekretow, ale komunikat nic nie wnosi
            raise UsosUnavailableError(f"{method}: {type(exc).__name__}") from None
        _raise_for_status(method, response)
        return response

    # --- laczenie konta (OAuth 1.0a "3-legged") ---------------------------

    def request_token(self) -> tuple[str, str]:
        """Nowy request token z adresem powrotu i uprawnieniami z ustawien.

        Returns:
            (oauth_token, oauth_token_secret).
        """
        response = self._post(
            "services/oauth/request_token",
            {"scopes": self._settings.scopes or None},
            callback=self._settings.callback_url,
        )
        return _token_pair(response)

    def authorize_url(self, request_token: str) -> str:
        """Adres strony zgody w USOS, na ktora frontend przekierowuje."""
        return self._base_url + "services/oauth/authorize?" + urlencode({"oauth_token": request_token})

    def access_token(self, request_token: str, request_secret: str, verifier: str) -> tuple[str, str]:
        """Wymienia autoryzowany request token (i verifier z callbacku) na
        token dostepu uzytkownika.

        Raises:
            UsosUnauthorizedError: request token wygasl, zostal juz uzyty albo
                verifier jest bledny.
        """
        response = self._post(
            "services/oauth/access_token", token=request_token, secret=request_secret, verifier=verifier
        )
        return _token_pair(response)

    # --- wywolania w imieniu uzytkownika -----------------------------------

    def call(self, token: UserToken, method: str, **params: Any) -> Any:
        """Metoda USOS API podpisana tokenem uzytkownika, np.
        call(token, "services/users/user", fields="id|first_name|last_name").

        Returns:
            Odpowiedz JSON.

        Raises:
            UsosUnauthorizedError: token odrzucony (401).
            UsosUnavailableError: USOS nie odpowiada.
            UsosApiError: inny blad (np. brak uprawnienia, zly parametr).
        """
        response = self._post(method, params, token=token.token, secret=token.secret)
        try:
            return response.json()
        except ValueError:
            raise UsosApiError(response.status_code, "invalid_json", f"{method}: response is not JSON") from None

    def revoke(self, token: UserToken) -> None:
        """Cofa token w USOS (services/oauth/revoke_token). Zgoda w USOS
        zostaje - uzytkownik moze ja odebrac na stronie USOS API."""
        self._post("services/oauth/revoke_token", token=token.token, secret=token.secret)
