"""CLI scrapera USOS - opis w __init__.py."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .api import Credentials, UsosApi, UsosError
from .context import DEFAULT_FACULTY, Context

DEFAULT_OUT = Path("data") / "usos"


def _scrape(args: argparse.Namespace) -> int:
    from .run import COLLECTOR_NAMES, run

    only = [name.strip() for name in args.only.split(",")] if args.only else None
    unknown = set(only or ()) - set(COLLECTOR_NAMES)
    if unknown:
        print(f"nieznane kolektory: {', '.join(sorted(unknown))} (sa: {', '.join(COLLECTOR_NAMES)})", file=sys.stderr)
        return 2
    credentials = Credentials.from_env()
    if not credentials.has_consumer:
        logging.getLogger("usos").warning("brak USOS_CONSUMER_KEY/SECRET - tylko dane dostepne bez klucza")
    ctx = Context(api=UsosApi(credentials, delay=args.delay), faculty=args.faculty)
    result = run(ctx, args.out, only=only, partial=args.partial, force=args.force)
    print(json.dumps({
        "written": result.written,
        "records": dict(result.counts),
        "kept": dict(result.kept),
        "carried": dict(result.carried),
        "failed": result.failed,
        "skipped": result.skipped,
        "shrunk": {kind: list(counts) for kind, counts in result.shrunk.items()},
        "suspicious": sorted(result.suspicious),
        "requests": ctx.api.requests,
        "warnings": len(ctx.warnings),
    }, ensure_ascii=False))
    return 0 if result.written else 1


def _call(args: argparse.Namespace) -> int:
    """Pojedyncze wywolanie metody (do sprawdzania ksztaltu odpowiedzi)."""
    params = {}
    for item in args.params:
        key, sep, value = item.partition("=")
        if not sep:
            print(f"parametr {item!r}: oczekiwano klucz=wartosc", file=sys.stderr)
            return 2
        params[key] = value
    api = UsosApi(Credentials.from_env(), delay=0)
    try:
        result = api.call(args.method, user=args.user, **params)
    except UsosError as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


COMMANDS = ("scrape", "call", "login")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    argv = list(sys.argv[1:] if argv is None else argv)
    # bez polecenia = scrape (python -m pipeline.scrapers.usos --only news)
    if not any(arg in COMMANDS for arg in argv):
        argv.insert(0, "scrape")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true")
    parser = argparse.ArgumentParser(prog="python -m pipeline.scrapers.usos", description="Scraper USOS UJ -> data/usos/")
    commands = parser.add_subparsers(dest="command", required=True)

    scrape = commands.add_parser("scrape", parents=[common], help="zbiera dane (domyslne polecenie)")
    scrape.add_argument("--out", type=Path, default=DEFAULT_OUT, help="katalog zbioru (domyslnie data/usos)")
    scrape.add_argument("--only", help="tylko wybrane kolektory (z zaleznosciami), po przecinku; reszta zbioru zostaje")
    scrape.add_argument("--partial", action="store_true", help="zapisz mimo pominietych lub nieudanych kolektorow")
    scrape.add_argument("--force", action="store_true", help="zapisz mimo duzego spadku liczby rekordow")
    scrape.add_argument("--faculty", default=DEFAULT_FACULTY, help="wydzial (domyslnie UJ.WMI)")
    scrape.add_argument("--delay", type=float, default=0.3, help="najmniejszy odstep miedzy zapytaniami [s]")

    call = commands.add_parser("call", parents=[common], help="wywoluje jedna metode USOS API i wypisuje JSON")
    call.add_argument("method", help="np. services/fac/faculty")
    call.add_argument("params", nargs="*", help="klucz=wartosc")
    call.add_argument("--user", action="store_true", help="podpisz tokenem uzytkownika (USOS_ACCESS_TOKEN)")
    commands.add_parser("login", parents=[common], help="jednorazowe logowanie operatora (token do adresow e-mail pracownikow)")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # naglowki OAuth, podpisy i adresy zapytan nie trafiaja do logow nawet z -v
    for name in ("urllib3", "oauthlib", "requests_oauthlib"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if args.command == "call":
        return _call(args)
    if args.command == "login":
        from .login import login

        login()
        return 0
    return _scrape(args)


if __name__ == "__main__":
    sys.exit(main())
