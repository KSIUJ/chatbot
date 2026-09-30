"""Kryptografia pomocnicza dla logowania: szyfrowanie tokenow, tokeny sesji, PKCE."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class DecryptionError(Exception):
    """Szyfrogram jest uszkodzony, wygasl albo zaszyfrowano go innym kluczem."""


class TokenCipher:
    """Szyfrowanie (Fernet = AES-128-CBC + HMAC) wartosci trzymanych w bazie i
    w ciasteczku logowania. Klucz jest wyprowadzany z AUTH_SECRET_KEY przez HKDF,
    wiec w env wystarczy dowolny dlugi losowy napis."""

    def __init__(self, secret_key: str) -> None:
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"chatbot-auth-token-encryption-v1",
        ).derive(secret_key.encode("utf-8"))
        self._fernet = Fernet(base64.urlsafe_b64encode(key))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str, max_age_seconds: int | None = None) -> str:
        """Odszyfrowuje; przy max_age_seconds odrzuca starsze szyfrogramy.

        Raises:
            DecryptionError: gdy szyfrogram jest niepoprawny albo za stary.
        """
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii"), ttl=max_age_seconds).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise DecryptionError("cannot decrypt value") from exc


def new_session_token() -> str:
    """Losowy token do ciasteczka sesji (256 bitow)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """SHA-256 tokenu - klucz sesji w bazie. Token ma pelna entropie, wiec sol
    ani wolny hash nie sa potrzebne."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def pkce_challenge(verifier: str) -> str:
    """code_challenge dla metody S256 (RFC 7636)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class LoginState:
    """Dane jednego logowania, zyjace miedzy /auth/login a /auth/callback.

    Trzymane w zaszyfrowanym ciasteczku przegladarki, ktora zaczela logowanie -
    to wiaze callback z ta przegladarka (ochrona przed login CSRF) bez tabeli
    w bazie, ktora moznaby zapchac anonimowymi requestami na /auth/login.
    """

    state: str
    nonce: str
    code_verifier: str

    @classmethod
    def generate(cls) -> LoginState:
        return cls(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(64),
        )

    @property
    def code_challenge(self) -> str:
        return pkce_challenge(self.code_verifier)

    def seal(self, cipher: TokenCipher) -> str:
        payload = {"s": self.state, "n": self.nonce, "v": self.code_verifier}
        return cipher.encrypt(json.dumps(payload, separators=(",", ":")))

    @classmethod
    def unseal(cls, sealed: str, cipher: TokenCipher, max_age_seconds: int) -> LoginState:
        """Odczytuje ciasteczko logowania.

        Raises:
            DecryptionError: ciasteczko podrobione, uszkodzone albo starsze niz max_age_seconds.
        """
        raw = cipher.decrypt(sealed, max_age_seconds=max_age_seconds)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DecryptionError("malformed login state") from exc
        if not isinstance(payload, dict):
            raise DecryptionError("malformed login state")
        state, nonce, verifier = payload.get("s"), payload.get("n"), payload.get("v")
        if not (isinstance(state, str) and isinstance(nonce, str) and isinstance(verifier, str)):
            raise DecryptionError("malformed login state")
        return cls(state=state, nonce=nonce, code_verifier=verifier)
