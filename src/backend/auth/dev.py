"""Tryb deweloperski (ENV=dev): zmyslone konta zamiast Keycloaka KSI.

DevOIDCClient ma interfejs OIDCClient, wiec reszta logowania dziala bez zmian:
/auth/login -> strona wyboru konta (/auth/dev/login, w miejscu formularza
Keycloaka) -> /auth/callback -> sesja w bazie, a przy kazdym zapytaniu
"userinfo" z grupami konta. Grupy wynikaja z OIDC_REQUIRED_GROUP i
OIDC_ADMIN_GROUP, wiec konta zachowuja sie jak prawdziwe osoby z tych grup.

Kody i tokeny to jawne napisy z id konta - nic tu nie jest tajne, bo kazdy,
kto dosiegnie backendu w tym trybie, i tak moze wybrac dowolne konto. Dlatego
main.py wpuszcza wtedy tylko zapytania z petli zwrotnej.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .oidc import (
    InvalidGrantError,
    JSONObject,
    OIDCClient,
    OIDCError,
    TokenSet,
    UserinfoUnauthorizedError,
)
from .settings import AuthSettings

ACCESS_TOKEN_LIFETIME = timedelta(hours=1)

_ACCESS_PREFIX = "dev-access:"
_REFRESH_PREFIX = "dev-refresh:"
_ID_PREFIX = "dev-id:"


@dataclass(frozen=True)
class DevAccount:
    id: str
    name: str
    username: str
    role: str
    member: bool
    admin: bool

    @property
    def email(self) -> str:
        return f"{self.username}@ksi.test"


# id = "sub" w Keycloaku: konto w bazie jest wiazane po nim, wiec historia
# rozmow kazdego konta zostaje miedzy logowaniami.
DEV_ACCOUNTS: tuple[DevAccount, ...] = (
    DevAccount("dev-zarzad", "Zofia Zarządowa", "zofia", "Zarząd - panel administratora", member=True, admin=True),
    DevAccount("dev-czlonek", "Czesław Członek", "czeslaw", "Członek KSI", member=True, admin=False),
    DevAccount("dev-czlonkini", "Celina Członkini", "celina", "Członkini KSI - druga osoba", member=True, admin=False),
    DevAccount("dev-byly", "Bartek Były", "bartek", "Bez grupy /Członek - odmowa dostępu", member=False, admin=False),
)


def find_account(account_id: str) -> DevAccount | None:
    return next((a for a in DEV_ACCOUNTS if a.id == account_id), None)


def _groups(account: DevAccount, settings: AuthSettings) -> list[str]:
    groups: list[str] = []
    if account.member:
        groups.append(settings.required_group)
    if account.admin and settings.admin_group is not None:
        groups.append(settings.admin_group)
    return groups


def _account_from(token: str, prefix: str, error: type[OIDCError]) -> DevAccount:
    account = find_account(token.removeprefix(prefix)) if token.startswith(prefix) else None
    if account is None:
        raise error("unknown dev account")
    return account


def dev_login_url(settings: AuthSettings) -> str:
    """Strona wyboru konta obok callbacku: .../api/auth/callback -> .../api/auth/dev/login
    (adres widziany przez przegladarke, przez proxy vite)."""
    base = settings.redirect_uri.rsplit("/", 1)[0]
    return f"{base}/dev/login"


class DevOIDCClient(OIDCClient):
    """Atrapa Keycloaka: te same metody co OIDCClient, bez sieci."""

    def __init__(self, settings: AuthSettings) -> None:  # noqa: D107 - bez klienta HTTP
        self._settings = settings

    def _tokens(self, account: DevAccount, nonce: str | None) -> TokenSet:
        return TokenSet(
            access_token=_ACCESS_PREFIX + account.id,
            access_token_expires_at=datetime.now(timezone.utc) + ACCESS_TOKEN_LIFETIME,
            refresh_token=_REFRESH_PREFIX + account.id,
            id_token=f"{_ID_PREFIX}{account.id}:{nonce}" if nonce is not None else None,
        )

    def build_authorization_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        ui_locales: str | None = None,
        prompt: str | None = None,
    ) -> str:
        return f"{dev_login_url(self._settings)}?{urlencode({'state': state, 'nonce': nonce})}"

    def exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        # kod = "<id konta>:<nonce>" ze strony wyboru konta
        account_id, _, nonce = code.partition(":")
        account = find_account(account_id)
        if account is None or not nonce:
            raise InvalidGrantError("unknown dev account")
        return self._tokens(account, nonce)

    def refresh(self, refresh_token: str) -> TokenSet:
        return self._tokens(_account_from(refresh_token, _REFRESH_PREFIX, InvalidGrantError), None)

    def userinfo(self, access_token: str) -> JSONObject:
        account = _account_from(access_token, _ACCESS_PREFIX, UserinfoUnauthorizedError)
        return {
            "sub": account.id,
            "name": account.name,
            "preferred_username": account.username,
            "email": account.email,
            self._settings.groups_claim: _groups(account, self._settings),
        }

    def validate_id_token(self, id_token: str, nonce: str) -> JSONObject:
        account_id, _, token_nonce = id_token.removeprefix(_ID_PREFIX).partition(":")
        account = find_account(account_id) if id_token.startswith(_ID_PREFIX) else None
        if account is None or token_nonce != nonce:
            raise OIDCError("invalid dev ID token")
        return {"sub": account.id, "name": account.name, "email": account.email}

    def build_logout_url(self, id_token_hint: str | None) -> str | None:
        # bez sesji SSO do zamkniecia: wracamy na strone glowna, ktora znow
        # przekieruje do wyboru konta (zmiana konta)
        return self._settings.post_logout_redirect_uri


def render_login_page(settings: AuthSettings, state: str, nonce: str) -> str:
    """Strona wyboru konta (w miejscu formularza Keycloaka)."""
    buttons = []
    for account in DEV_ACCOUNTS:
        query = urlencode({"code": f"{account.id}:{nonce}", "state": state})
        buttons.append(
            f'<a class="account" href="{html.escape(settings.redirect_uri)}?{html.escape(query)}">'
            f"<span>{html.escape(account.name)}</span><small>{html.escape(account.role)}</small></a>"
        )
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Logowanie (tryb dev)</title>
<style>
  :root {{ color-scheme: light dark; --bg: #eceef3; --card: #fff; --fg: #2a2b3d; --muted: #6b6f80;
    --line: #d9dbe3; --warn-bg: #f7ece9; --warn-fg: #9b2c1c; --warn-line: #e2b4a9; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #17181f; --card: #22232d; --fg: #ececf1;
    --muted: #a3a6b5; --line: #3a3c4a; --warn-bg: #3a2420; --warn-fg: #f2b8aa; --warn-line: #6b3a30; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px;
    background: var(--bg); color: var(--fg); font: 16px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ width: 100%; max-width: 440px; background: var(--card); border: 1px solid var(--line);
    border-radius: 12px; padding: 32px 28px; }}
  h1 {{ margin: 0 0 4px; font-size: 22px; text-align: center; }}
  p {{ margin: 0 0 20px; color: var(--muted); text-align: center; font-size: 14px; }}
  .warn {{ background: var(--warn-bg); color: var(--warn-fg); border: 1px solid var(--warn-line);
    border-radius: 8px; padding: 10px 12px; font-size: 14px; margin-bottom: 16px; }}
  .account {{ display: flex; flex-direction: column; gap: 2px; padding: 12px 14px; margin-top: 8px;
    border: 1px solid var(--line); border-radius: 8px; color: inherit; text-decoration: none; }}
  .account:hover, .account:focus-visible {{ border-color: var(--fg); outline: none; }}
  .account small {{ color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
<main>
  <h1>Chatbot WMiI UJ</h1>
  <p>Logowanie w trybie deweloperskim</p>
  <div class="warn">Tryb dev (ENV=dev) - zmyślone konta zamiast Keycloaka KSI. Wybierz konto.</div>
  {"".join(buttons)}
</main>
</body>
</html>
"""
