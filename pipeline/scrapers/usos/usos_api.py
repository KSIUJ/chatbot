"""
Wspolny rdzen klienta USOS API UJ dla scrape_staff.py i usos_login.py:
podpisywanie zapytan (OAuth1), limit tempa zapytan i zapis surowych odpowiedzi.
"""

import json
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1

load_dotenv()

BASE_URL = "https://apps.usos.uj.edu.pl/"
REQUEST_TIMEOUT = 30

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RATE_LIMIT_FILE = os.path.join(SCRIPT_DIR, ".last_request_time")
MIN_REQUEST_INTERVAL_SECONDS = 1.0

RAW_DATA_DIR = os.path.join("data", "usos", "raw")


class UsosApiError(Exception):
    """Podniesiony, gdy USOS API odpowie statusem HTTP innym niz 200."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"USOS API error {status_code}: {body}")


class UsosCredentialsError(RuntimeError):
    """Podniesiony, gdy w .env brakuje kluczy USOS."""


def respect_rate_limit() -> None:
    """Wymusza minimum MIN_REQUEST_INTERVAL_SECONDS odstepu miedzy zapytaniami.

    Stan jest w pliku, bo skrypty uzywajace modulu to osobne procesy CLI.
    """
    last_request = None

    if os.path.exists(RATE_LIMIT_FILE):
        try:
            with open(RATE_LIMIT_FILE, "r", encoding="utf-8") as f:
                last_request = float(f.read().strip())
        except (ValueError, OSError):
            last_request = None

    if last_request is not None:
        elapsed = time.time() - last_request
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            wait_time = MIN_REQUEST_INTERVAL_SECONDS - elapsed
            print(f"[rate limit] Czekam {wait_time:.2f}s przed kolejnym zapytaniem...")
            time.sleep(wait_time)

    with open(RATE_LIMIT_FILE, "w", encoding="utf-8") as f:
        f.write(str(time.time()))


def build_url(method_path: str) -> str:
    """Pelny adres metody API, np. "services/users/user"."""
    return BASE_URL.rstrip("/") + "/" + method_path.lstrip("/")


def usos_get(
    method_path: str, params: dict[str, str] | None = None, auth: OAuth1 | None = None
) -> requests.Response:
    """GET do USOS API z limitem tempa; status inny niz 200 -> UsosApiError."""
    respect_rate_limit()
    url = build_url(method_path)
    response = requests.get(url, params=params or {}, auth=auth, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)
    return response


def save_response(method_path: str, payload: dict, output_dir: str) -> str:
    """Zapisuje surowa odpowiedz JSON do pliku i zwraca jego sciezke."""
    os.makedirs(output_dir, exist_ok=True)

    safe_method_name = method_path.strip("/").replace("/", "_")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{safe_method_name}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filepath


def get_consumer_credentials() -> tuple[str, str]:
    """Zwraca (consumer_key, consumer_secret) z .env albo podnosi UsosCredentialsError."""
    consumer_key = os.getenv("USOS_CONSUMER_KEY")
    consumer_secret = os.getenv("USOS_CONSUMER_SECRET")
    if not consumer_key or not consumer_secret:
        raise UsosCredentialsError(
            "Brak USOS_CONSUMER_KEY/USOS_CONSUMER_SECRET w .env. Zarejestruj "
            "aplikacje na https://apps.usos.uj.edu.pl/developers/ i uzupelnij "
            ".env na podstawie .env.example."
        )
    return consumer_key, consumer_secret


def _get_access_token_credentials() -> tuple[str, str]:
    """Zwraca (access_token, access_token_secret) zapisane w .env przez usos_login.py."""
    access_token = os.getenv("USOS_ACCESS_TOKEN")
    access_token_secret = os.getenv("USOS_ACCESS_TOKEN_SECRET")
    if not access_token or not access_token_secret:
        raise UsosCredentialsError(
            "Brak USOS_ACCESS_TOKEN/USOS_ACCESS_TOKEN_SECRET w .env. Uruchom "
            "najpierw pipeline/scrapers/usos/usos_login.py, zeby zalogowac sie do USOS "
            "i uzyskac access token."
        )
    return access_token, access_token_secret


def usos_call_signed(method_path: str, params: dict[str, str] | None = None) -> dict:
    """GET podpisany kluczem consumer (2-legged OAuth1, bez logowania uzytkownika)."""
    consumer_key, consumer_secret = get_consumer_credentials()
    print(f"[request][signed] GET {build_url(method_path)} params={params or {}}")
    return usos_get(method_path, params, OAuth1(consumer_key, consumer_secret)).json()


def usos_call_authenticated(method_path: str, params: dict[str, str] | None = None) -> dict:
    """GET podpisany pelnym 3-legged OAuth1 (consumer + access token uzytkownika).

    Jedyny tryb, ktory odblokowuje pola wymagajace scope'ow uzytkownika (np.
    email pod scope'em other_emails).
    """
    consumer_key, consumer_secret = get_consumer_credentials()
    access_token, access_token_secret = _get_access_token_credentials()
    auth = OAuth1(
        consumer_key,
        consumer_secret,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )
    print(f"[request][authenticated] GET {build_url(method_path)} params={params or {}}")
    return usos_get(method_path, params, auth).json()
