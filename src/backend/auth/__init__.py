"""Logowanie przez Keycloak KSI (OIDC) - dostep tylko dla czlonkow wymaganej grupy."""

from .dependencies import require_admin, require_member, require_member_context, verify_origin
from .router import router
from .settings import get_auth_settings

__all__ = [
    "get_auth_settings",
    "require_admin",
    "require_member",
    "require_member_context",
    "router",
    "verify_origin",
]
