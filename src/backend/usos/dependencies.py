"""Zaleznosci FastAPI dla polaczen z USOS: konfiguracja, klient USOS API
i szyfrowanie tokenow w bazie."""

from __future__ import annotations

from functools import lru_cache

import httpx
from fastapi import Depends

from ..auth.dependencies import auth_error
from ..auth.settings import AuthSettings, get_auth_settings
from .client import UsosClient
from .crypto import UsosTokenCipher
from .settings import UsosSettings, get_usos_settings


@lru_cache(maxsize=4)
def _client_for(settings: UsosSettings) -> UsosClient:
    http = httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=False)
    return UsosClient(settings, http)


@lru_cache(maxsize=4)
def _token_cipher_for(secret_key: str) -> UsosTokenCipher:
    return UsosTokenCipher(secret_key)


def get_usos_client(settings: UsosSettings = Depends(get_usos_settings)) -> UsosClient:
    """Klient USOS API (testy podmieniaja go na atrape przez dependency_overrides)."""
    return _client_for(settings)


def get_usos_token_cipher(auth: AuthSettings = Depends(get_auth_settings)) -> UsosTokenCipher:
    return _token_cipher_for(auth.secret_key)


def require_usos_available(settings: UsosSettings = Depends(get_usos_settings)) -> UsosSettings:
    """Konfiguracja USOS, o ile funkcja jest wlaczona.

    Raises:
        HTTPException: 503 usos_unavailable (brak klucza aplikacji albo USOS_CONNECT=off).
    """
    if not settings.available:
        raise auth_error(503, "usos_unavailable", "Polaczenie z USOS jest niedostepne.")
    return settings
