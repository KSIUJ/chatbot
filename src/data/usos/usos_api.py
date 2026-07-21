"""
Wspolny rdzen klienta USOS API UJ - uzywany zarowno przez eksploracyjny
CLI (usos_client.py) jak i przez wlasciwy scraper (scrape_staff.py).
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
    """Podniesiony, gdy brakuje USOS_CONSUMER_KEY/USOS_CONSUMER_SECRET w .env."""


def _respect_rate_limit() -> None:
    """Wymusza minimum MIN_REQUEST_INTERVAL_SECONDS odstepu miedzy zapytaniami.

    Stan trzymany jest w pliku (nie tylko w pamieci procesu), bo skrypty
    korzystajace z tego modulu sa uruchamiane jako osobne procesy CLI.
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


def usos_call_anonymous(method_path: str, params: dict[str, str] | None = None) -> dict:
    """Wykonuje anonimowe (bez klucza/OAuth) zapytanie GET do USOS API.

    Zwraca sparsowany JSON. Jesli serwer odpowie statusem innym niz 200,
    podnosi UsosApiError zamiast po cichu polykac blad.
    """
    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/" + method_path.lstrip("/")

    print(f"[request] GET {url} params={params or {}}")
    response = requests.get(url, params=params or {}, timeout=30)

    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)

    return response.json()


def _get_consumer_credentials() -> tuple[str, str]:
    """Zwraca (consumer_key, consumer_secret) z .env.

    Podnosi UsosCredentialsError, jesli ktorykolwiek brakuje.
    """
    consumer_key = os.getenv("USOS_CONSUMER_KEY")
    consumer_secret = os.getenv("USOS_CONSUMER_SECRET")
    if not consumer_key or not consumer_secret:
        raise UsosCredentialsError(
            "Brak USOS_CONSUMER_KEY/USOS_CONSUMER_SECRET w .env. Zarejestruj "
            "aplikacje na https://apps.usos.uj.edu.pl/developers/ i uzupelnij "
            ".env na podstawie .env.example."
        )
    return consumer_key, consumer_secret


def usos_call_signed(method_path: str, params: dict[str, str] | None = None) -> dict:
    """Wykonuje zapytanie GET podpisane kluczem consumer (2-legged OAuth1).

    To NIE jest pelny 3-legged flow - nie loguje zadnego uzytkownika, tylko
    podpisuje zapytanie kluczem consumer/secret zarejestrowanej aplikacji.
    Wymaga USOS_CONSUMER_KEY i USOS_CONSUMER_SECRET w .env (patrz
    .env.example).
    """
    consumer_key, consumer_secret = _get_consumer_credentials()

    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/" + method_path.lstrip("/")
    auth = OAuth1(consumer_key, consumer_secret)

    print(f"[request][signed] GET {url} params={params or {}}")
    response = requests.get(url, params=params or {}, auth=auth, timeout=30)

    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)

    return response.json()


def usos_call_authenticated(method_path: str, params: dict[str, str] | None = None) -> dict:
    """STUB - wywolanie USOS API w trybie uwierzytelnionym (3-legged OAuth 1.0a).

    NIEZAIMPLEMENTOWANE. Do zrobienia zanim ta funkcja bedzie uzywalna:

    1. Zarejestrowac aplikacje na https://apps.usos.uj.edu.pl/developers/
       i uzyskac USOS_CONSUMER_KEY / USOS_CONSUMER_SECRET (patrz .env.example).
    2. Pobrac tymczasowy "request token" z endpointu
       services/oauth/request_token (podpisany kluczem consumer key/secret,
       np. przez requests_oauthlib.OAuth1).
    3. Przekierowac uzytkownika do services/oauth/authorize z request tokenem,
       zeby zalogowal sie w USOS i zaakceptowal dostep aplikacji.
    4. Odebrac "oauth_verifier" (redirect callback lub recznie wpisany PIN).
    5. Wymienic request token + verifier na "access token" przez
       services/oauth/access_token.
    6. Zapisac access token + access token secret (np. lokalnie, NIE w repo).
    7. Kazde kolejne zapytanie podpisywac pelnym zestawem
       consumer key/secret + access token/secret (OAuth1 w requests_oauthlib).

    Nie jest potrzebne dla scrapera pracownikow WMI - services/users/user i
    services/users/staff_index wymagaja tylko podpisu kluczem consumer
    (patrz usos_call_signed), bez pelnego logowania uzytkownika.
    """
    raise NotImplementedError(
        "usos_call_authenticated nie jest jeszcze zaimplementowane - "
        "na razie uzywaj usos_call_anonymous() lub usos_call_signed(). "
        "Zobacz docstring tej funkcji po liste krokow do zrobienia (3-legged OAuth)."
    )
