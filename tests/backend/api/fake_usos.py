"""Atrapa USOS API dla testow polaczenia kont (httpx.MockTransport).

Kazde zapytanie jest sprawdzane wlasna, niezalezna od oauthlib implementacja
podpisu OAuth 1.0a HMAC-SHA1 (RFC 5849, 3.4) - zly podpis = 401, jak w USOS.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, quote, unquote, urlencode

import httpx

CONSUMER_KEY = "TestConsumerKey123"
CONSUMER_SECRET = "TestConsumerSecret456"
BASE = "https://apps.usos.uj.edu.pl/"

_HEADER_PARAM = re.compile(r'([A-Za-z0-9_]+)="([^"]*)"')


def _enc(value: str) -> str:
    """Kodowanie procentowe RFC 3986 (RFC 5849, 3.6): bez zmian tylko A-Z a-z 0-9 - . _ ~"""
    return quote(value, safe="~")


def oauth_header_params(request: httpx.Request) -> dict[str, str]:
    header = request.headers.get("authorization", "")
    if not header.startswith("OAuth "):
        return {}
    return {key: unquote(value) for key, value in _HEADER_PARAM.findall(header[len("OAuth "):])}


def form_params(request: httpx.Request) -> list[tuple[str, str]]:
    if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        return parse_qsl(request.content.decode("utf-8"), keep_blank_values=True)
    return []


def signature_valid(request: httpx.Request, consumer_secret: str, token_secret: str) -> bool:
    oauth = oauth_header_params(request)
    signature = oauth.pop("oauth_signature", None)
    oauth.pop("realm", None)
    if signature is None or oauth.get("oauth_signature_method") != "HMAC-SHA1":
        return False
    params = [*oauth.items(), *form_params(request), *parse_qsl(request.url.query.decode("ascii"))]
    normalized = "&".join(f"{k}={v}" for k, v in sorted((_enc(k), _enc(v)) for k, v in params))
    base_uri = f"{request.url.scheme.lower()}://{request.url.host.lower()}{request.url.path}"
    base_string = "&".join([request.method.upper(), _enc(base_uri), _enc(normalized)])
    key = f"{_enc(consumer_secret)}&{_enc(token_secret)}"
    expected = base64.b64encode(hmac.new(key.encode(), base_string.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


def _token() -> str:
    return secrets.token_hex(10)


@dataclass
class _RequestToken:
    secret: str
    callback: str
    scopes: str
    verifier: str | None = None
    used: bool = False


@dataclass
class _AccessToken:
    secret: str
    usos_id: str


@dataclass
class UsosPerson:
    id: str
    first_name: str
    last_name: str


@dataclass
class FakeUsos:
    """Minimalny USOS API: request_token, authorize (symulowany), access_token,
    users/user, revoke_token i dowolna metoda zwracajaca {"ok": true}."""

    people: dict[str, UsosPerson] = field(default_factory=lambda: {"123": UsosPerson("123", "Jan", "Kowalski")})
    request_tokens: dict[str, _RequestToken] = field(default_factory=dict)
    access_tokens: dict[str, _AccessToken] = field(default_factory=dict)
    revoked: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    # wymuszone odpowiedzi: nazwa metody -> status HTTP (np. 503, 500)
    fail: dict[str, int] = field(default_factory=dict)
    # users/user zwraca to zamiast danych osoby
    user_override: object | None = None

    # --- sterowanie z testow ---

    def authorize(self, authorize_url: str, usos_id: str = "123") -> tuple[str, str]:
        """Symuluje zgode w USOS; zwraca (oauth_token, oauth_verifier) do callbacku."""
        assert authorize_url.startswith(BASE + "services/oauth/authorize?")
        token = dict(parse_qsl(authorize_url.split("?", 1)[1]))["oauth_token"]
        pending = self.request_tokens[token]
        pending.verifier = str(secrets.randbelow(10**8)).zfill(8)
        self._authorized_for = usos_id
        return token, pending.verifier

    def last_access_token(self) -> tuple[str, str]:
        token = next(reversed(self.access_tokens))
        return token, self.access_tokens[token].secret

    # --- transport ---

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(BASE), request.url
        method = request.url.path.lstrip("/")
        self.calls.append(method)
        if request.method != "POST":
            return httpx.Response(405)
        if method in self.fail:
            return httpx.Response(self.fail[method], json={"message": "forced failure"})
        oauth = oauth_header_params(request)
        if oauth.get("oauth_consumer_key") != CONSUMER_KEY:
            return httpx.Response(401, text="invalid consumer")
        timestamp = int(oauth.get("oauth_timestamp", "0"))
        if abs(time.time() - timestamp) > 300 or not oauth.get("oauth_nonce"):
            return httpx.Response(401, text="bad timestamp or nonce")

        if method == "services/oauth/request_token":
            if not signature_valid(request, CONSUMER_SECRET, ""):
                return httpx.Response(401, text="invalid signature")
            callback = oauth.get("oauth_callback")
            if not callback:
                return httpx.Response(400, json={"message": "oauth_callback missing", "error": "param_missing"})
            token = _token()
            self.request_tokens[token] = _RequestToken(
                secret=_token(), callback=callback, scopes=dict(form_params(request)).get("scopes", "")
            )
            body = urlencode({
                "oauth_token": token,
                "oauth_token_secret": self.request_tokens[token].secret,
                "oauth_callback_confirmed": "true",
            })
            return httpx.Response(200, text=body)

        token = oauth.get("oauth_token", "")
        if method == "services/oauth/access_token":
            pending = self.request_tokens.get(token)
            if pending is None or pending.used or not signature_valid(request, CONSUMER_SECRET, pending.secret):
                return httpx.Response(401, text="invalid request token")
            if pending.verifier is None or oauth.get("oauth_verifier") != pending.verifier:
                return httpx.Response(401, text="invalid verifier")
            pending.used = True
            access = _token()
            self.access_tokens[access] = _AccessToken(secret=_token(), usos_id=self._authorized_for)
            return httpx.Response(200, text=urlencode({"oauth_token": access, "oauth_token_secret": self.access_tokens[access].secret}))

        granted = self.access_tokens.get(token)
        if granted is None or not signature_valid(request, CONSUMER_SECRET, granted.secret):
            return httpx.Response(401, json={"message": "Invalid access token"})
        if method == "services/oauth/revoke_token":
            del self.access_tokens[token]
            self.revoked.append(token)
            return httpx.Response(200, json={"success": True})
        if method == "services/users/user":
            if self.user_override is not None:
                return httpx.Response(200, content=json.dumps(self.user_override))
            person = self.people[granted.usos_id]
            fields = dict(form_params(request)).get("fields", "id|first_name|last_name").split("|")
            data = {"id": person.id, "first_name": person.first_name, "last_name": person.last_name}
            return httpx.Response(200, json={k: v for k, v in data.items() if k in fields})
        return httpx.Response(200, json={"ok": True, "params": dict(form_params(request))})
