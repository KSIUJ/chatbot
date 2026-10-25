"""
Klient USOS API UJ (https://apps.usos.uj.edu.pl/developers/api/).

Trzy poziomy dostepu:
- bez klucza - czesc metod (przedmioty, plan zajec, budynki, jednostki),
- z kluczem aplikacji (USOS_CONSUMER_KEY/SECRET, OAuth1 "2-legged") -
  wiekszosc danych publicznych (pracownicy, aktualnosci, rejestracje,
  kalendarz),
- z tokenem uzytkownika (USOS_ACCESS_TOKEN/SECRET, "3-legged") - dane
  widoczne po zalogowaniu; scraper uzywa go tylko, jesli jest ustawiony.

Metoda wymagajaca klucza, gdy go nie ma, konczy sie ConsumerRequired - kolektor
pomija wtedy swoja czesc zamiast przerywac caly przebieg. Zapytania sa
wysylane nie czesciej niz co `delay` sekund, a bledy chwilowe (429, 5xx,
zerwane polaczenie) sa ponawiane z rosnacym odstepem.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import requests
from requests_oauthlib import OAuth1

from ..common.throttle import Throttle, backoff_seconds

logger = logging.getLogger(__name__)

BASE_URL = "https://apps.usos.uj.edu.pl/"
TIMEOUT = 30
DEFAULT_DELAY = 0.3
RETRIES = 4
RETRY_STATUSES = {429, 502, 503, 504}
# 500 USOS zwraca tez przy blednych parametrach (np. cykl, w ktorym przedmiotu nie ma) -
# ponawiany tylko raz
RETRIES_500 = 1
# tyle kolejnych zapytan z bledem chwilowym (po ponowieniach) = USOS niedostepne
MAX_CONSECUTIVE_FAILURES = 5
USER_AGENT = "KSI-chatbot-scraper/1.0 (+https://chat.ksi.sh; usos)"
# najwiecej id w jednym wywolaniu metod "wiele naraz" (users/users, courses/courses, ...)
BATCH_SIZE = 50


class UsosError(RuntimeError):
    """Blad USOS API (status HTTP i tresc odpowiedzi)."""

    def __init__(self, method: str, status: int, body: str):
        self.method = method
        self.status = status
        self.body = body
        super().__init__(f"{method}: HTTP {status}: {body[:300]}")


class ConsumerRequired(UsosError):
    """Metoda wymaga klucza aplikacji, a scraper go nie ma."""


class UsosUnavailable(RuntimeError):
    """Kolejne zapytania koncza sie bledami chwilowymi - przerwac przebieg zamiast
    meczyc API setkami ponowien (bezpiecznik). Nie dziedziczy po UsosError, wiec
    kolektory pomijajace pojedyncze obiekty go nie polykaja."""


@dataclass(frozen=True)
class Credentials:
    consumer_key: str = ""
    consumer_secret: str = ""
    token: str = ""
    token_secret: str = ""

    @classmethod
    def from_env(cls) -> Credentials:
        return cls(
            consumer_key=os.getenv("USOS_CONSUMER_KEY", "").strip(),
            consumer_secret=os.getenv("USOS_CONSUMER_SECRET", "").strip(),
            token=os.getenv("USOS_ACCESS_TOKEN", "").strip(),
            token_secret=os.getenv("USOS_ACCESS_TOKEN_SECRET", "").strip(),
        )

    @property
    def has_consumer(self) -> bool:
        return bool(self.consumer_key and self.consumer_secret)

    @property
    def has_token(self) -> bool:
        return self.has_consumer and bool(self.token and self.token_secret)


def fields(*names: str) -> str:
    """Selektor pol USOS API: fields("id", "name") -> "id|name"."""
    return "|".join(names)


def chunks(items: Iterable[Any], size: int = BATCH_SIZE) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


class UsosApi:
    def __init__(
        self,
        credentials: Credentials | None = None,
        *,
        base_url: str = BASE_URL,
        delay: float = DEFAULT_DELAY,
        session: requests.Session | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.credentials = credentials or Credentials()
        self.base_url = base_url.rstrip("/") + "/"
        self.delay = delay
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self._sleep = sleep
        self._throttle = Throttle(delay, sleep=sleep, clock=clock)
        # statystyki przebiegu (raport na koncu)
        self.requests = 0
        self.errors = 0
        self._failures_in_row = 0

    @property
    def has_consumer(self) -> bool:
        return self.credentials.has_consumer

    def _auth(self, user: bool) -> OAuth1 | None:
        c = self.credentials
        if not c.has_consumer:
            return None
        if user and c.has_token:
            return OAuth1(c.consumer_key, c.consumer_secret, resource_owner_key=c.token, resource_owner_secret=c.token_secret)
        return OAuth1(c.consumer_key, c.consumer_secret)

    def call(self, method: str, *, user: bool = False, **params: Any) -> Any:
        """Wywolanie metody, np. call("services/fac/faculty", fac_id="UJ.WMI").

        Parametry None sa pomijane, listy laczone "|", bool jako true/false.
        `user` - podpisz tokenem uzytkownika, jesli jest (inaczej samym kluczem).

        Raises:
            ConsumerRequired: metoda wymaga klucza aplikacji, a go nie ma.
            UsosError: inny blad (po wyczerpaniu ponowien dla bledow chwilowych).
        """
        if self._failures_in_row >= MAX_CONSECUTIVE_FAILURES:
            raise UsosUnavailable(f"{method}: USOS API niedostepne ({self._failures_in_row} kolejnych bledow chwilowych)")
        data = {key: _param(value) for key, value in params.items() if value is not None}
        url = self.base_url + method.strip("/")
        auth = self._auth(user)
        for attempt in range(RETRIES + 1):
            self._throttle.wait()
            self.requests += 1
            try:
                # POST zalecany przez dokumentacje (dlugie selektory pol, listy id); bez
                # przekierowan - API nigdzie nie odsyla, a podpis nie powinien isc dalej
                response = self.session.post(url, data=data, auth=auth, timeout=TIMEOUT, allow_redirects=False)
            except requests.RequestException as error:
                if attempt == RETRIES:
                    raise self._transient_failure(UsosError(method, 0, str(error))) from error
                self._backoff(method, attempt, None, str(error))
                continue
            status = response.status_code
            if status == 200:
                self._failures_in_row = 0
                try:
                    return response.json()
                except ValueError as error:
                    # np. strona HTML przerwy technicznej
                    self.errors += 1
                    raise UsosError(method, status, response.text) from error
            retries = RETRIES_500 if status == 500 else RETRIES if status in RETRY_STATUSES else 0
            if attempt < retries:
                self._backoff(method, attempt, response.headers.get("Retry-After"), f"HTTP {status}")
                continue
            error = (ConsumerRequired if _consumer_missing(response) else UsosError)(method, status, response.text)
            if status in RETRY_STATUSES:
                raise self._transient_failure(error)
            self._failures_in_row = 0
            self.errors += 1
            raise error
        raise AssertionError("unreachable")

    def _transient_failure(self, error: UsosError) -> UsosError:
        self.errors += 1
        self._failures_in_row += 1
        return error

    def _backoff(self, method: str, attempt: int, retry_after: str | None, reason: str) -> None:
        wait = backoff_seconds(attempt, retry_after)
        logger.warning("%s: %s, ponawiam za %.0f s", method, reason, wait)
        self._sleep(wait)

    def batch(self, method: str, id_param: str, ids: Iterable[str], **params: Any) -> dict[str, Any]:
        """Metody "wiele naraz" (zwracaja slownik id -> obiekt albo null),
        wolane partiami po BATCH_SIZE id. Brakujace obiekty (null) pomija."""
        result: dict[str, Any] = {}
        for part in chunks(dict.fromkeys(str(i) for i in ids)):
            got = self.call(method, **{id_param: part}, **params)
            result.update({key: value for key, value in (got or {}).items() if value is not None})
        return result

    def pages(self, method: str, items_key: str = "items", num: int = 100, limit: int | None = None, **params: Any) -> Iterator[Any]:
        """Wyniki stronicowane (start/num + next_page)."""
        start = 0
        while True:
            got = self.call(method, start=start, num=num, **params)
            items = got.get(items_key) or []
            yield from items
            start += len(items)
            if not got.get("next_page") or not items or (limit is not None and start >= limit):
                return


def _param(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return "|".join(str(v) for v in value)
    return str(value)


def _consumer_missing(response: requests.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("reason") == "consumer_missing"
