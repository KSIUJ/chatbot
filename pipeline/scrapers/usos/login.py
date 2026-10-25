"""
Jednorazowe logowanie operatora scrapera do USOS API (OAuth1 "3-legged",
tryb PIN - bez serwera z callbackiem). Token z uprawnieniem other_emails
pozwala pobrac adresy e-mail pracownikow (collectors/staff.py); offline_access
- token nie wygasa po 2 godzinach. Token trafia do .env (USOS_ACCESS_TOKEN,
USOS_ACCESS_TOKEN_SECRET) i nie jest wypisywany na ekran.

    python -m pipeline.scrapers.usos login
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs

from dotenv import find_dotenv
from requests_oauthlib import OAuth1

from .api import BASE_URL, TIMEOUT, USER_AGENT, Credentials

SCOPES = "other_emails|offline_access"
# tokeny USOS to znaki alfanumeryczne - nic innego (np. nowa linia) nie trafi do .env
_TOKEN = re.compile(r"[A-Za-z0-9]{8,128}")


def _form(text: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(text).items()}


def _token(form: dict[str, str], key: str) -> str:
    value = form.get(key, "")
    if not _TOKEN.fullmatch(value):
        raise SystemExit(f"USOS zwrocil nieoczekiwany {key} - przerywam (nic nie zapisano)")
    return value


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Podmienia albo dopisuje zmienne w .env, reszte zostawia bez zmian. Zapis
    atomowy (plik tymczasowy tylko dla wlasciciela, potem podmiana) - przerwany
    zapis nie zostawi uszkodzonego .env z sekretami produkcji."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
    remaining = dict(updates)
    for i, line in enumerate(lines):
        name = line.removeprefix("export ").split("=", 1)[0].strip()
        if name in remaining:
            lines[i] = f"{name}={remaining.pop(name)}\n"
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines += [f"{key}={value}\n" for key, value in remaining.items()]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write("".join(lines))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def login(env_path: Path | None = None, ask=input, session=None) -> None:
    import requests

    credentials = Credentials.from_env()
    if not credentials.has_consumer:
        raise SystemExit("brak USOS_CONSUMER_KEY/SECRET w .env")
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)

    auth = OAuth1(credentials.consumer_key, credentials.consumer_secret, callback_uri="oob")
    response = session.post(BASE_URL + "services/oauth/request_token", data={"scopes": SCOPES}, auth=auth, timeout=TIMEOUT)
    response.raise_for_status()
    request = _form(response.text)
    _token(request, "oauth_token")

    print("Otworz w przegladarce, zaloguj sie do USOS i zaakceptuj dostep:")
    print(f"{BASE_URL}services/oauth/authorize?oauth_token={request['oauth_token']}")
    verifier = ask("PIN pokazany przez USOS: ").strip()

    auth = OAuth1(
        credentials.consumer_key, credentials.consumer_secret,
        resource_owner_key=request["oauth_token"], resource_owner_secret=request["oauth_token_secret"], verifier=verifier,
    )
    response = session.post(BASE_URL + "services/oauth/access_token", auth=auth, timeout=TIMEOUT)
    response.raise_for_status()
    access = _form(response.text)
    # ten sam .env, ktory wczytal load_dotenv() (szukany od biezacego katalogu w gore)
    env_path = env_path or Path(find_dotenv(usecwd=True) or ".env")
    update_env_file(env_path, {
        "USOS_ACCESS_TOKEN": _token(access, "oauth_token"),
        "USOS_ACCESS_TOKEN_SECRET": _token(access, "oauth_token_secret"),
    })
    print(f"[ok] token zapisany w {env_path}")
