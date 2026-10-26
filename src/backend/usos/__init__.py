"""Polaczenie konta czatu z USOS (OAuth 1.0a, USOS API UJ): tokeny
uzytkownikow zaszyfrowane w bazie, do wywolan w ich imieniu."""

from .router import router
from .settings import get_usos_settings

__all__ = ["get_usos_settings", "router"]
