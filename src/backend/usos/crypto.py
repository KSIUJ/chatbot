"""Szyfrowanie tokenow USOS w bazie i ciasteczko laczenia z USOS.

Token uzytkownika (oauth_token + oauth_token_secret) lezy w bazie jako JEDEN
szyfrogram Fernet z osobnym kluczem (HKDF z AUTH_SECRET_KEY, inne `info` niz
sesje logowania). Tresc to JSON {"uid", "t", "s", "v"}: uid wiaze szyfrogram
z kontem - wiersz przepisany na inne konto (np. przez kogos z dostepem do
bazy) nie da sie odszyfrowac jako token tego konta.
"""

from __future__ import annotations

import hmac
import json
import time
from dataclasses import dataclass, field

from ..auth.crypto import DecryptionError, TokenCipher

USOS_TOKEN_KEY_INFO = b"chatbot-usos-token-v1"
_TOKEN_FORMAT_VERSION = 1
# znacznik celu w ciasteczku laczenia - szyfrogram z innego miejsca (np.
# ciasteczko logowania, ten sam klucz) nie przejdzie jako ConnectState
_CONNECT_PURPOSE = "usos-connect"


@dataclass(frozen=True)
class UserToken:
    """Odszyfrowany token USOS jednego konta. repr=False: sekrety nie trafiaja
    do logow, tracebackow ani komunikatow bledow."""

    user_id: str
    token: str = field(repr=False)
    secret: str = field(repr=False)


class UsosTokenCipher:
    """Szyfruje token USOS razem z id konta i sprawdza je przy odczycie."""

    def __init__(self, secret_key: str) -> None:
        self._cipher = TokenCipher(secret_key, info=USOS_TOKEN_KEY_INFO)

    def seal(self, user_id: str, token: str, secret: str) -> str:
        payload = {"uid": user_id, "t": token, "s": secret, "v": _TOKEN_FORMAT_VERSION}
        return self._cipher.encrypt(json.dumps(payload, separators=(",", ":")))

    def unseal(self, user_id: str, ciphertext: str) -> UserToken:
        """Odszyfrowuje token konta `user_id`.

        Raises:
            DecryptionError: szyfrogram uszkodzony, z innym kluczem, w nieznanym
                formacie albo nalezacy do innego konta.
        """
        raw = self._cipher.decrypt(ciphertext)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DecryptionError("malformed usos token") from exc
        if not isinstance(payload, dict) or payload.get("v") != _TOKEN_FORMAT_VERSION:
            raise DecryptionError("unknown usos token format")
        uid, token, secret = payload.get("uid"), payload.get("t"), payload.get("s")
        if not (isinstance(uid, str) and isinstance(token, str) and isinstance(secret, str)):
            raise DecryptionError("malformed usos token")
        if not hmac.compare_digest(uid.encode("utf-8"), user_id.encode("utf-8")):
            raise DecryptionError("usos token belongs to another account")
        return UserToken(user_id=user_id, token=token, secret=secret)


@dataclass(frozen=True)
class ConnectState:
    """Dane jednego laczenia z USOS, zyjace miedzy POST /usos/connect a
    GET /usos/callback, w zaszyfrowanym ciasteczku przegladarki, ktora je
    zaczela (jak LoginState przy logowaniu). user_id wiaze je z kontem:
    callback w sesji innego konta jest odrzucany."""

    request_token: str
    request_secret: str = field(repr=False)
    user_id: str
    scopes: str
    created_at: int

    @classmethod
    def new(cls, request_token: str, request_secret: str, user_id: str, scopes: str) -> ConnectState:
        return cls(
            request_token=request_token,
            request_secret=request_secret,
            user_id=user_id,
            scopes=scopes,
            created_at=int(time.time()),
        )

    def seal(self, cipher: TokenCipher) -> str:
        payload = {
            "p": _CONNECT_PURPOSE,
            "t": self.request_token,
            "s": self.request_secret,
            "u": self.user_id,
            "sc": self.scopes,
            "c": self.created_at,
        }
        return cipher.encrypt(json.dumps(payload, separators=(",", ":")))

    @classmethod
    def unseal(cls, sealed: str, cipher: TokenCipher, max_age_seconds: int) -> ConnectState:
        """Odczytuje ciasteczko laczenia.

        Raises:
            DecryptionError: ciasteczko podrobione, uszkodzone, z innego celu
                albo starsze niz max_age_seconds.
        """
        raw = cipher.decrypt(sealed, max_age_seconds=max_age_seconds)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DecryptionError("malformed usos connect state") from exc
        if not isinstance(payload, dict) or payload.get("p") != _CONNECT_PURPOSE:
            raise DecryptionError("malformed usos connect state")
        token, secret, user_id, scopes, created = (
            payload.get("t"), payload.get("s"), payload.get("u"), payload.get("sc"), payload.get("c"),
        )
        if not (
            isinstance(token, str) and isinstance(secret, str) and isinstance(user_id, str)
            and isinstance(scopes, str) and isinstance(created, int)
        ):
            raise DecryptionError("malformed usos connect state")
        return cls(request_token=token, request_secret=secret, user_id=user_id, scopes=scopes, created_at=created)
