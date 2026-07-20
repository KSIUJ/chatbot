"""
Eksploracyjny klient CLI do USOS API UJ.

Cel: reczne sprawdzanie, jakie dane faktycznie zwraca dana metoda API USOS,
zanim powstanie docelowy scraper. Domyslnie dziala anonimowo (bez klucza);
z flaga --signed podpisuje zapytanie kluczem consumer (patrz
usos_api.usos_call_signed) dla metod, ktore tego wymagaja.

Przyklad uzycia:
    python usos_client.py services/fac/fac2 --params fac_id=WMI
    python usos_client.py services/users/user --signed --params user_id=12345
"""

import argparse
import json
import sys

from usos_api import (
    RAW_DATA_DIR,
    UsosApiError,
    UsosCredentialsError,
    save_response,
    usos_call_anonymous,
    usos_call_signed,
)


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksploracyjny klient CLI do USOS API UJ."
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
    parser.add_argument(
        "--signed",
        action="store_true",
        help="Podpisz zapytanie kluczem consumer (2-legged OAuth1), wymaga .env",
    )
    args = parser.parse_args()

    try:
        params = parse_params(args.params)
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.signed:
            payload = usos_call_signed(args.method_path, params)
        else:
            payload = usos_call_anonymous(args.method_path, params)
    except UsosApiError as e:
        print(f"[error] Status HTTP: {e.status_code}", file=sys.stderr)
        print(f"[error] Tresc odpowiedzi:\n{e.body}", file=sys.stderr)
        sys.exit(1)
    except UsosCredentialsError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    saved_path = save_response(args.method_path, payload, RAW_DATA_DIR)
    print(f"\n[saved] {saved_path}")


if __name__ == "__main__":
    main()
