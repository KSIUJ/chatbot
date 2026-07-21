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

from usos_api import BASE_URL

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
