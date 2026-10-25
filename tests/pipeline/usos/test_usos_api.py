"""Klient USOS API (pipeline/scrapers/usos/api.py): parametry, podpis,
ponowienia, brak klucza, partie i stronicowanie - bez sieci."""

from __future__ import annotations

import pytest
import requests

from pipeline.scrapers.usos.api import BATCH_SIZE, ConsumerRequired, Credentials, UsosApi, UsosError


class Response:
    def __init__(self, status, body=None, headers=None, text=""):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = text or (str(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.posts = []

    def post(self, url, data=None, auth=None, timeout=None, allow_redirects=True):
        assert allow_redirects is False
        self.posts.append({"url": url, "data": data, "auth": auth})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _api(responses, credentials=None):
    sleeps = []
    session = Session(responses)
    api = UsosApi(credentials, session=session, delay=0, sleep=sleeps.append)
    return api, session, sleeps


def test_params_are_encoded_and_none_dropped():
    api, session, _ = _api([Response(200, {"ok": True})])

    assert api.call("services/x/y", ids=["a", "b"], flag=True, skip=None, n=3) == {"ok": True}

    post = session.posts[0]
    assert post["url"] == "https://apps.usos.uj.edu.pl/services/x/y"
    assert post["data"] == {"ids": "a|b", "flag": "true", "n": "3"}
    assert post["auth"] is None


def test_consumer_key_signs_requests_and_token_only_for_user_calls():
    creds = Credentials("key", "secret", "tok", "toksecret")
    api, session, _ = _api([Response(200, {}), Response(200, {})], creds)

    api.call("services/a")
    api.call("services/b", user=True)

    plain, user = (p["auth"] for p in session.posts)
    assert plain.client.client_key == "key" and plain.client.resource_owner_key is None
    assert user.client.resource_owner_key == "tok"


def test_transient_errors_are_retried_with_backoff():
    api, session, sleeps = _api([
        Response(503, text="busy"),
        requests.ConnectionError("reset"),
        Response(429, text="slow down", headers={"Retry-After": "30"}),
        Response(200, {"done": 1}),
    ])

    assert api.call("services/a") == {"done": 1}
    assert len(session.posts) == 4
    assert sleeps == [2.0, 4.0, 30.0]


def test_missing_consumer_key_is_a_distinct_error():
    body = {"message": "Consumer signature is required.", "error": "method_forbidden", "reason": "consumer_missing"}
    api, _, _ = _api([Response(401, body)])

    with pytest.raises(ConsumerRequired):
        api.call("services/news/search")


def test_other_errors_are_not_retried():
    api, session, _ = _api([Response(400, {"error": "param_missing"})])

    with pytest.raises(UsosError) as error:
        api.call("services/a")
    assert error.value.status == 400 and len(session.posts) == 1


def test_delay_between_requests():
    now = [100.0]
    sleeps = []
    session = Session([Response(200, {}), Response(200, {})])
    api = UsosApi(session=session, delay=0.5, sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)), clock=lambda: now[0])

    api.call("services/a")
    now[0] += 0.2
    api.call("services/b")

    assert sleeps == [pytest.approx(0.3)]


def test_batch_splits_ids_and_drops_missing():
    ids = [str(i) for i in range(BATCH_SIZE + 3)]
    first = {i: {"id": i} for i in ids[:BATCH_SIZE]}
    first["0"] = None
    api, session, _ = _api([Response(200, first), Response(200, {i: {"id": i} for i in ids[BATCH_SIZE:]})])

    got = api.batch("services/users/users", "user_ids", ids + ["1"], fields="id")

    assert set(got) == set(ids) - {"0"}
    assert [len(p["data"]["user_ids"].split("|")) for p in session.posts] == [BATCH_SIZE, 3]


def test_pages_follow_next_page():
    api, session, _ = _api([
        Response(200, {"items": [1, 2], "next_page": True}),
        Response(200, {"items": [3], "next_page": False}),
    ])

    assert list(api.pages("services/x", num=2)) == [1, 2, 3]
    assert [p["data"]["start"] for p in session.posts] == ["0", "2"]


def test_non_json_200_is_a_usos_error():
    api, _, _ = _api([Response(200, None, text="<html>przerwa techniczna</html>")])

    with pytest.raises(UsosError) as error:
        api.call("services/a")
    assert error.value.status == 200


def test_500_is_retried_once_and_retry_after_is_capped():
    api, session, sleeps = _api([
        Response(500, text="err"), Response(500, text="err"),
        Response(429, text="x", headers={"Retry-After": "86400"}), Response(200, {}),
    ])

    with pytest.raises(UsosError):
        api.call("services/a")
    assert len(session.posts) == 2

    api.call("services/b")
    assert sleeps[-1] == 300.0


def test_circuit_breaker_after_consecutive_transient_failures():
    from pipeline.scrapers.usos.api import MAX_CONSECUTIVE_FAILURES, RETRIES, UsosUnavailable

    api, session, _ = _api([Response(503, text="down")] * ((RETRIES + 1) * MAX_CONSECUTIVE_FAILURES))
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        with pytest.raises(UsosError):
            api.call("services/a")

    with pytest.raises(UsosUnavailable):
        api.call("services/a")
    assert len(session.posts) == (RETRIES + 1) * MAX_CONSECUTIVE_FAILURES


def test_redirects_are_not_followed():
    api, session, _ = _api([Response(302, text="", headers={"Location": "https://evil.example"})])

    with pytest.raises(UsosError):
        api.call("services/a")
