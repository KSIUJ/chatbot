"""
Jednorazowy, interaktywny login do USOS API UJ (pelny 3-legged OAuth1).

Uzycie: python usos_login.py

Wymaga USOS_CONSUMER_KEY/USOS_CONSUMER_SECRET juz ustawionych w .env (patrz
.env.example). Po pomyslnym zalogowaniu zapisuje USOS_ACCESS_TOKEN i
USOS_ACCESS_TOKEN_SECRET do .env - te wartosci sa potem uzywane przez
usos_call_authenticated() (usos_api.py) i flage --with-email w
scrape_staff.py.

Uzywa trybu "oob" (out-of-band): zamiast lokalnego serwera z callbackiem,
USOS pokazuje uzytkownikowi PIN po zalogowaniu i zaakceptowaniu dostepu,
ktory trzeba wpisac w tym skrypcie.
"""

from urllib.parse import parse_qs

import requests
from requests_oauthlib import OAuth1

from usos_api import BASE_URL, UsosApiError, _get_consumer_credentials, _respect_rate_limit

SCOPES = "other_emails|offline_access"


def parse_oauth_response(text: str) -> dict[str, str]:
    """Parsuje odpowiedz w formacie form-encoded (oauth_token=...&...)."""
    parsed = parse_qs(text)
    return {key: values[0] for key, values in parsed.items()}


def build_authorize_url(oauth_token: str) -> str:
    """Buduje URL, ktory uzytkownik ma otworzyc w przegladarce, zeby sie zalogowac."""
    return f"{BASE_URL.rstrip('/')}/services/oauth/authorize?oauth_token={oauth_token}"


def update_env_file(path: str, updates: dict[str, str]) -> None:
    """Aktualizuje lub dopisuje zmienne w pliku .env, zachowujac reszte bez zmian."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    remaining = dict(updates)
    for i, line in enumerate(lines):
        for key in list(remaining):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={remaining.pop(key)}\n"
                break

    for key, value in remaining.items():
        lines.append(f"{key}={value}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def get_request_token() -> tuple[str, str]:
    """Pobiera niezautoryzowany request token, podpisany kluczem consumer."""
    consumer_key, consumer_secret = _get_consumer_credentials()
    auth = OAuth1(consumer_key, consumer_secret, callback_uri="oob")

    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/services/oauth/request_token"
    response = requests.get(
        url, params={"oauth_callback": "oob", "scopes": SCOPES}, auth=auth, timeout=30
    )

    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)

    parsed = parse_oauth_response(response.text)
    return parsed["oauth_token"], parsed["oauth_token_secret"]


def exchange_for_access_token(
    oauth_token: str, oauth_token_secret: str, oauth_verifier: str
) -> tuple[str, str]:
    """Wymienia autoryzowany request token + PIN na docelowy access token."""
    consumer_key, consumer_secret = _get_consumer_credentials()
    auth = OAuth1(
        consumer_key,
        consumer_secret,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_token_secret,
        verifier=oauth_verifier,
    )

    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/services/oauth/access_token"
    response = requests.get(url, auth=auth, timeout=30)

    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)

    parsed = parse_oauth_response(response.text)
    return parsed["oauth_token"], parsed["oauth_token_secret"]


def main() -> None:
    oauth_token, oauth_token_secret = get_request_token()

    print("Otworz ten URL w przegladarce, zaloguj sie do USOS i zaakceptuj dostep:")
    print(build_authorize_url(oauth_token))
    print()
    oauth_verifier = input("Wklej tutaj PIN pokazany przez USOS: ").strip()

    access_token, access_token_secret = exchange_for_access_token(
        oauth_token, oauth_token_secret, oauth_verifier
    )

    update_env_file(
        ".env",
        {
            "USOS_ACCESS_TOKEN": access_token,
            "USOS_ACCESS_TOKEN_SECRET": access_token_secret,
        },
    )

    print("\n[ok] Zapisano USOS_ACCESS_TOKEN i USOS_ACCESS_TOKEN_SECRET do .env.")


if __name__ == "__main__":
    main()
