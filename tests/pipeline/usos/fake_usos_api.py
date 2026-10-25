"""Atrapa UsosApi dla testow kolektorow: odpowiedzi wedlug metody (funkcja
parametrow albo gotowa wartosc), zapis wywolan, brak sieci."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from pipeline.scrapers.usos.api import ConsumerRequired, UsosApi
from pipeline.scrapers.usos.context import Context, Term

TERM = Term("26/27Z", "Semestr zimowy 2026/2027", date(2026, 10, 1), date(2027, 1, 28))


class FakeApi(UsosApi):
    def __init__(self, responses: dict[str, Any], consumer: bool = True):
        super().__init__(delay=0, sleep=lambda _s: None)
        self.responses = responses
        self.consumer = consumer
        self.calls: list[tuple[str, dict]] = []

    @property
    def has_consumer(self) -> bool:
        return self.consumer

    def call(self, method: str, *, user: bool = False, **params: Any) -> Any:
        self.calls.append((method, {**params, "user": True} if user else params))
        self.requests += 1
        if method not in self.responses:
            raise AssertionError(f"nieoczekiwane wywolanie {method} {params}")
        response = self.responses[method]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, Callable):
            return response(**params)
        return response

    def methods(self) -> list[str]:
        return [method for method, _params in self.calls]


def consumer_required(method: str) -> ConsumerRequired:
    return ConsumerRequired(method, 401, '{"reason": "consumer_missing"}')


def context(responses: dict[str, Any], consumer: bool = True, **fields: Any) -> Context:
    ctx = Context(api=FakeApi(responses, consumer), today=date(2026, 10, 25))
    for key, value in fields.items():
        setattr(ctx, key, value)
    return ctx
