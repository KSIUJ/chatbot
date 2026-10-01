"""Atrapa Keycloaka dla testow API (httpx.MockTransport + prawdziwie
podpisane ID tokeny) i pomocnik do pelnego logowania."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import ECKey

ISSUER = "https://auth.test/realms/ksi"
CLIENT_ID = "chatbot"
CLIENT_SECRET = "test-client-secret"
REDIRECT_URI = "https://chat.test/api/auth/callback"
MEMBER_GROUP = "/Członek"


@dataclass
class FakeUser:
    sub: str
    groups: list[str]
    email: str
    name: str
    username: str


@dataclass
class _PendingCode:
    sub: str
    nonce: str
    code_challenge: str
    redirect_uri: str


@dataclass
class FakeKeycloak:
    """Minimalny Keycloak: discovery, JWKS, token (code + refresh z rotacja),
    userinfo liczone na biezaco z `users` (jak w prawdziwym Keycloaku)."""

    access_ttl: int = 300
    down: bool = False
    users: dict[str, FakeUser] = field(default_factory=dict)
    codes: dict[str, _PendingCode] = field(default_factory=dict)
    access_tokens: dict[str, str] = field(default_factory=dict)
    refresh_tokens: dict[str, str] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    nonce_override: str | None = None
    # False = klient bez mappera Group Membership: userinfo nie ma claimu "groups"
    groups_mapper: bool = True
    # gdy ustawiony, ID tokeny sa podpisywane nim, a JWKS nadal oglasza `key`
    signing_key_override: ECKey | None = None

    def __post_init__(self) -> None:
        self.key = ECKey.generate_key("P-256", parameters={"kid": "k1", "alg": "ES256", "use": "sig"})

    # --- sterowanie z testow ---

    def add_user(self, sub: str, groups: list[str] | None = None) -> FakeUser:
        user = FakeUser(
            sub=sub,
            groups=list(groups if groups is not None else [MEMBER_GROUP]),
            email=f"{sub}@student.uj.edu.pl",
            name=f"{sub.title()} Testowy",
            username=sub,
        )
        self.users[sub] = user
        return user

    def authorize(self, authorization_url: str, sub: str) -> tuple[str, str]:
        """Symuluje zalogowanie uzytkownika w Keycloaku; zwraca (code, state)."""
        query = {k: v[0] for k, v in parse_qs(urlsplit(authorization_url).query).items()}
        assert query["client_id"] == CLIENT_ID
        assert query["response_type"] == "code"
        assert query["code_challenge_method"] == "S256"
        assert "openid" in query["scope"].split()
        code = secrets.token_urlsafe(16)
        self.codes[code] = _PendingCode(sub, query["nonce"], query["code_challenge"], query["redirect_uri"])
        return code, query["state"]

    def end_sessions(self, sub: str) -> None:
        """Wylogowanie/zablokowanie w Keycloaku - wszystkie tokeny przepadaja."""
        self.access_tokens = {t: s for t, s in self.access_tokens.items() if s != sub}
        self.refresh_tokens = {t: s for t, s in self.refresh_tokens.items() if s != sub}

    # --- wydawanie tokenow ---

    def _id_token(self, sub: str, nonce: str, **overrides: object) -> str:
        now = int(time.time())
        user = self.users[sub]
        claims: dict[str, object] = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "azp": CLIENT_ID,
            "sub": sub,
            "iat": now,
            "exp": now + 300,
            "nonce": nonce,
            "email": user.email,
            "name": user.name,
            "preferred_username": user.username,
        }
        claims.update(overrides)
        return jwt.encode({"alg": "ES256", "kid": "k1"}, claims, self.signing_key_override or self.key)

    def _issue(self, sub: str, nonce: str | None) -> dict[str, object]:
        access = secrets.token_urlsafe(16)
        refresh = secrets.token_urlsafe(16)
        self.access_tokens[access] = sub
        self.refresh_tokens[refresh] = sub
        body: dict[str, object] = {
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": self.access_ttl,
            "token_type": "Bearer",
        }
        if nonce is not None:
            body["id_token"] = self._id_token(sub, self.nonce_override or nonce)
        return body

    # --- HTTP ---

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if self.down:
            raise httpx.ConnectError("keycloak is down", request=request)
        base = "/realms/ksi/protocol/openid-connect"
        if path == "/realms/ksi/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
                "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
                "userinfo_endpoint": f"{ISSUER}/protocol/openid-connect/userinfo",
                "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
                "end_session_endpoint": f"{ISSUER}/protocol/openid-connect/logout",
            })
        if path == f"{base}/certs":
            return httpx.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if path == f"{base}/token":
            return self._token(dict(parse_qs(request.content.decode())))
        if path == f"{base}/userinfo":
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            sub = self.access_tokens.get(token)
            if sub is None or sub not in self.users:
                return httpx.Response(401, json={"error": "invalid_token"})
            user = self.users[sub]
            claims = {
                "sub": sub,
                "email": user.email,
                "name": user.name,
                "preferred_username": user.username,
            }
            if self.groups_mapper:
                claims["groups"] = list(user.groups)
            return httpx.Response(200, json=claims)
        return httpx.Response(404)

    def _token(self, form_lists: dict[str, list[str]]) -> httpx.Response:
        form = {k: v[0] for k, v in form_lists.items()}
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return httpx.Response(401, json={"error": "invalid_client"})
        if form.get("grant_type") == "authorization_code":
            pending = self.codes.pop(form.get("code", ""), None)
            if pending is None or pending.redirect_uri != form.get("redirect_uri"):
                return httpx.Response(400, json={"error": "invalid_grant"})
            digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
            if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != pending.code_challenge:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "PKCE"})
            return httpx.Response(200, json=self._issue(pending.sub, pending.nonce))
        if form.get("grant_type") == "refresh_token":
            # rotacja: stary refresh token jest uniewazniany
            sub = self.refresh_tokens.pop(form.get("refresh_token", ""), None)
            if sub is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json=self._issue(sub, None))
        return httpx.Response(400, json={"error": "unsupported_grant_type"})



def login(client: TestClient, keycloak: FakeKeycloak, sub: str = "alice", groups: list[str] | None = None) -> httpx.Response:
    """Pelne logowanie: /auth/login -> (Keycloak) -> /auth/callback."""
    if sub not in keycloak.users:
        keycloak.add_user(sub, groups)
    start = client.get("/auth/login", follow_redirects=False)
    assert start.status_code == 303, start.text
    code, state = keycloak.authorize(start.headers["location"], sub)
    return client.get("/auth/callback", params={"code": code, "state": state}, follow_redirects=False)
