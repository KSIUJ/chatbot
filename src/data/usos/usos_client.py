"""
Eksploracyjny klient CLI do USOS API UJ.

Cel: reczne sprawdzanie, jakie dane faktycznie zwraca dana metoda API USOS,
zanim powstanie docelowy scraper. Dziala WYLACZNIE w trybie anonimowym
(bez klucza API, bez OAuth) - dokladnie tak jak dopuszcza to poziom
"anonimowy" USOS API (zwykle zapytania HTTP GET).

Przyklad uzycia:
    python usos_client.py services/fac/fac2 --params fac_id=WMI
    python usos_client.py services/apiref/method --params name=services/fac/fac2
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://apps.usos.uj.edu.pl/"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RATE_LIMIT_FILE = os.path.join(SCRIPT_DIR, ".last_request_time")
MIN_REQUEST_INTERVAL_SECONDS = 1.0

RAW_DATA_DIR = os.path.join("data", "usos", "raw")


def _respect_rate_limit() -> None:
    """Wymusza minimum MIN_REQUEST_INTERVAL_SECONDS odstepu miedzy zapytaniami.

    Stan trzymany jest w pliku (nie tylko w pamieci procesu), bo skrypt jest
    uruchamiany jako osobny proces CLI za kazdym razem.
    """
    now = time.monotonic()
    last_request = None

    if os.path.exists(RATE_LIMIT_FILE):
        try:
            with open(RATE_LIMIT_FILE, "r", encoding="utf-8") as f:
                last_request = float(f.read().strip())
        except (ValueError, OSError):
            last_request = None

    if last_request is not None:
        elapsed_wall = time.time() - last_request
        if elapsed_wall < MIN_REQUEST_INTERVAL_SECONDS:
            wait_time = MIN_REQUEST_INTERVAL_SECONDS - elapsed_wall
            print(f"[rate limit] Czekam {wait_time:.2f}s przed kolejnym zapytaniem...")
            time.sleep(wait_time)

    with open(RATE_LIMIT_FILE, "w", encoding="utf-8") as f:
        f.write(str(time.time()))


def parse_params(raw_params: list[str]) -> dict[str, str]:
    """Parsuje liste 'klucz=wartosc' na slownik parametrow GET."""
    params: dict[str, str] = {}
    for raw in raw_params:
        if "=" not in raw:
            raise ValueError(
                f"Nieprawidlowy parametr '{raw}' - oczekiwano formatu klucz=wartosc"
            )
        key, value = raw.split("=", 1)
        params[key] = value
    return params


def save_response(method_path: str, payload: dict) -> str:
    """Zapisuje surowa odpowiedz JSON do pliku i zwraca jego sciezke."""
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    safe_method_name = method_path.strip("/").replace("/", "_")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{safe_method_name}_{timestamp}.json"
    filepath = os.path.join(RAW_DATA_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filepath


def usos_call_anonymous(method_path: str, params: dict[str, str] | None = None) -> dict:
    """Wykonuje anonimowe (bez klucza/OAuth) zapytanie GET do USOS API.

    Zwraca sparsowany JSON. Jesli serwer odpowie statusem innym niz 200,
    wypisuje status i tresc odpowiedzi na stderr i konczy proces (sys.exit),
    zamiast po cichu polykac blad.
    """
    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/" + method_path.lstrip("/")

    print(f"[request] GET {url} params={params or {}}")
    response = requests.get(url, params=params or {}, timeout=30)

    if response.status_code != 200:
        print(f"[error] Status HTTP: {response.status_code}", file=sys.stderr)
        print(f"[error] Tresc odpowiedzi:\n{response.text}", file=sys.stderr)
        sys.exit(1)

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

    Wymagana dodatkowa zaleznosc: requests_oauthlib (nie jest jeszcze
    dodana do requirements.txt - dodac razem z implementacja).
    """
    raise NotImplementedError(
        "usos_call_authenticated nie jest jeszcze zaimplementowane - "
        "na razie uzywaj wylacznie usos_call_anonymous(). Zobacz docstring "
        "tej funkcji po liste krokow do zrobienia (3-legged OAuth)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksploracyjny klient CLI do anonimowego USOS API UJ."
    )
    parser.add_argument(
        "method_path",
        help="Sciezka metody API, np. services/fac/fac2",
    )
    parser.add_argument(
        "--params",
        nargs="*",
        default=[],
        metavar="KEY=VALUE",
        help="Opcjonalne parametry GET, np. --params fac_id=WMI lang=en",
    )
    args = parser.parse_args()

    try:
        params = parse_params(args.params)
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)

    payload = usos_call_anonymous(args.method_path, params)

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    saved_path = save_response(args.method_path, payload)
    print(f"\n[saved] {saved_path}")


if __name__ == "__main__":
    main()
