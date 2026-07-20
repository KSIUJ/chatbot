# USOS Staff Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real scraper that pulls WMI staff contact info and office hours ("dyżury") from USOS API UJ into a normalized JSON dataset for the KSI RAG pipeline.

**Architecture:** A shared `usos_api.py` module (anonymous GET, 2-legged consumer-signed GET, rate limiting, raw-response saving) used by both the existing exploratory `usos_client.py` CLI and the new `scrape_staff.py` batch scraper. `scrape_staff.py` paginates `services/users/staff_index` to discover staff IDs, fetches each via `services/users/user` (signed), normalizes the free-text `office_hours`/`interests` `LangDict` fields, and writes both raw responses and a combined normalized dataset.

**Tech Stack:** Python 3.12, `requests`, `requests_oauthlib` (new), `python-dotenv`, `pytest` + `unittest.mock` (new, dev-only, no live network calls in tests).

## Global Constraints

- Target faculty is hardcoded to `fac_id=WMI` — not exposed as a CLI argument in this iteration.
- No `teachers_only` filtering — all staff members of WMI are included (the API's own default for this parameter is already `false`, so it is simply not passed).
- Minimum 1 second between any two USOS API requests, enforced via a single persisted rate-limit file shared by every script that calls the API (`usos_client.py` and `scrape_staff.py` alike).
- Per-employee fetch failures are logged to stderr and skipped, not retried, and do not abort the run. Whole-run failures (missing consumer credentials, `staff_index` itself failing) abort immediately with a clear message.
- No exceptions are silently swallowed. The only handled failure case is "non-200 HTTP status"; everything else propagates.
- Raw API responses always go to `data/usos/raw/`. The normalized staff dataset goes to `data/usos/staff/`.
- `requests_oauthlib` is a new dependency (`requirements.txt`). `pytest` is a new dev-only dependency (`requirements-dev.txt`, new file).
- No unit test hits the live USOS API — every HTTP call is mocked via `unittest.mock.patch`.

---

## File Structure

- `src/data/usos/usos_api.py` — **new**. Shared core: `UsosApiError`, `UsosCredentialsError`, `_respect_rate_limit`, `save_response`, `usos_call_anonymous`, `usos_call_signed`, `usos_call_authenticated` (3-legged stub, moved as-is), plus the module constants (`BASE_URL`, `RATE_LIMIT_FILE`, `RAW_DATA_DIR`).
- `src/data/usos/usos_client.py` — **modified**. Becomes a thin CLI over `usos_api.py`; adds `--signed` flag; keeps `parse_params` and `main`.
- `src/data/usos/scrape_staff.py` — **new**. The real scraper: `flatten_langdict`, `normalize_employee`, `fetch_all_staff_ids`, `fetch_employee_detail`, `save_staff_dataset`, `run_scrape`, `main`.
- `requirements.txt` — **modified**. Add `requests_oauthlib`.
- `requirements-dev.txt` — **new**. `pytest`.
- `tests/data/usos/conftest.py` — **new**. Adds `src/data/usos/` to `sys.path` so tests can `import usos_api`, `import usos_client`, `import scrape_staff` as top-level modules (matching how they're run in production — flat scripts, no package).
- `tests/data/usos/test_usos_api.py` — **new**.
- `tests/data/usos/test_usos_client.py` — **new**.
- `tests/data/usos/test_scrape_staff.py` — **new**.

---

### Task 1: Shared `usos_api.py` core (rate limiter, save_response, anonymous call)

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/data/usos/conftest.py`
- Create: `src/data/usos/usos_api.py`
- Test: `tests/data/usos/test_usos_api.py`

**Interfaces:**
- Produces: `usos_api.UsosApiError(status_code: int, body: str)` (has `.status_code`, `.body` attributes), `usos_api.BASE_URL: str`, `usos_api.RATE_LIMIT_FILE: str`, `usos_api.RAW_DATA_DIR: str`, `usos_api._respect_rate_limit() -> None`, `usos_api.save_response(method_path: str, payload: dict, output_dir: str) -> str`, `usos_api.usos_call_anonymous(method_path: str, params: dict | None = None) -> dict`.

- [ ] **Step 1: Create `requirements-dev.txt` and install it**

```
pytest
```

Run: `pip install -r requirements-dev.txt`
Expected: pytest installs successfully.

- [ ] **Step 2: Create the tests package path helper**

Create `tests/data/usos/conftest.py`:

```python
import os
import sys

SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "data", "usos")
)
sys.path.insert(0, SRC_DIR)
```

- [ ] **Step 3: Write the failing tests for the rate limiter and save_response**

Create `tests/data/usos/test_usos_api.py`:

```python
import json
import time

import pytest

import usos_api


def test_respect_rate_limit_waits_if_called_too_soon(tmp_path, monkeypatch):
    rate_limit_file = tmp_path / ".last_request_time"
    monkeypatch.setattr(usos_api, "RATE_LIMIT_FILE", str(rate_limit_file))

    fixed_time = 1000.0
    monkeypatch.setattr(time, "time", lambda: fixed_time)
    rate_limit_file.write_text(str(fixed_time - 0.3), encoding="utf-8")

    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleep_calls.append(seconds))

    usos_api._respect_rate_limit()

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(0.7, abs=0.01)
    assert rate_limit_file.read_text(encoding="utf-8") == str(fixed_time)


def test_respect_rate_limit_no_wait_if_enough_time_passed(tmp_path, monkeypatch):
    rate_limit_file = tmp_path / ".last_request_time"
    monkeypatch.setattr(usos_api, "RATE_LIMIT_FILE", str(rate_limit_file))

    fixed_time = 1000.0
    monkeypatch.setattr(time, "time", lambda: fixed_time)
    rate_limit_file.write_text(str(fixed_time - 5.0), encoding="utf-8")

    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleep_calls.append(seconds))

    usos_api._respect_rate_limit()

    assert sleep_calls == []


def test_save_response_writes_file_and_returns_path(tmp_path):
    path = usos_api.save_response("services/fac/fac2", {"a": 1}, str(tmp_path))

    assert os.path.exists(path)
    assert os.path.basename(path).startswith("services_fac_fac2_")
    assert os.path.basename(path).endswith(".json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"a": 1}


def test_usos_call_anonymous_returns_json_on_200(monkeypatch):
    monkeypatch.setattr(usos_api, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True}

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(usos_api.requests, "get", fake_get)

    result = usos_api.usos_call_anonymous("services/fac/fac2", {"fac_id": "WMI"})

    assert result == {"ok": True}
    assert captured["url"] == "https://apps.usos.uj.edu.pl/services/fac/fac2"
    assert captured["params"] == {"fac_id": "WMI"}


def test_usos_call_anonymous_raises_on_non_200(monkeypatch):
    monkeypatch.setattr(usos_api, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 400
        text = "bad request"

    monkeypatch.setattr(usos_api.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(usos_api.UsosApiError) as exc_info:
        usos_api.usos_call_anonymous("services/fac/fac2", {})

    assert exc_info.value.status_code == 400
    assert exc_info.value.body == "bad request"
```

Add `import os` at the top of `test_usos_api.py` alongside the existing imports (needed by `test_save_response_writes_file_and_returns_path`).

- [ ] **Step 4: Run tests to verify they fail (module doesn't exist yet)**

Run: `pytest tests/data/usos/test_usos_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'usos_api'`.

- [ ] **Step 5: Create `src/data/usos/usos_api.py` with the implementation**

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_usos_api.py -v`
Expected: PASS (6 tests).

- [ ] **Step 7: Commit**

```bash
git add requirements-dev.txt tests/data/usos/conftest.py tests/data/usos/test_usos_api.py src/data/usos/usos_api.py
git commit -m "Add shared usos_api core module with anonymous call and rate limiter"
```

---

### Task 2: `usos_call_signed` (2-legged OAuth1) in `usos_api.py`

**Files:**
- Modify: `requirements.txt`
- Modify: `src/data/usos/usos_api.py`
- Test: `tests/data/usos/test_usos_api.py`

**Interfaces:**
- Consumes: `usos_api.UsosApiError`, `usos_api._respect_rate_limit`, `usos_api.BASE_URL` (from Task 1).
- Produces: `usos_api.UsosCredentialsError(RuntimeError)`, `usos_api.usos_call_signed(method_path: str, params: dict | None = None) -> dict`.

- [ ] **Step 1: Add `requests_oauthlib` to `requirements.txt` and install it**

`requirements.txt` becomes:

```
requests
python-dotenv
requests_oauthlib
```

Run: `pip install -r requirements.txt`
Expected: `requests_oauthlib` installs successfully.

- [ ] **Step 2: Write the failing tests**

Append to `tests/data/usos/test_usos_api.py`:

```python
from requests_oauthlib import OAuth1


def test_usos_call_signed_raises_without_credentials(monkeypatch):
    monkeypatch.delenv("USOS_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("USOS_CONSUMER_SECRET", raising=False)

    with pytest.raises(usos_api.UsosCredentialsError):
        usos_api.usos_call_signed("services/users/user", {"user_id": "1"})


def test_usos_call_signed_sends_oauth1_auth_and_returns_json(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_api, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": 1}

    captured = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["auth"] = auth
        return FakeResponse()

    monkeypatch.setattr(usos_api.requests, "get", fake_get)

    result = usos_api.usos_call_signed("services/users/user", {"user_id": "1"})

    assert result == {"id": 1}
    assert captured["url"] == "https://apps.usos.uj.edu.pl/services/users/user"
    assert captured["params"] == {"user_id": "1"}
    assert isinstance(captured["auth"], OAuth1)


def test_usos_call_signed_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_api, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 403
        text = "forbidden"

    monkeypatch.setattr(usos_api.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(usos_api.UsosApiError) as exc_info:
        usos_api.usos_call_signed("services/users/user", {"user_id": "1"})

    assert exc_info.value.status_code == 403
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_usos_api.py -v`
Expected: FAIL with `AttributeError: module 'usos_api' has no attribute 'usos_call_signed'`.

- [ ] **Step 4: Implement `usos_call_signed` in `usos_api.py`**

Add near the top of `src/data/usos/usos_api.py`, after the `requests`/`dotenv` imports:

```python
from requests_oauthlib import OAuth1
```

Add after `UsosApiError`:

```python
class UsosCredentialsError(RuntimeError):
    """Podniesiony, gdy brakuje USOS_CONSUMER_KEY/USOS_CONSUMER_SECRET w .env."""
```

Add after `usos_call_anonymous`:

```python
def usos_call_signed(method_path: str, params: dict[str, str] | None = None) -> dict:
    """Wykonuje zapytanie GET podpisane kluczem consumer (2-legged OAuth1).

    To NIE jest pelny 3-legged flow - nie loguje zadnego uzytkownika, tylko
    podpisuje zapytanie kluczem consumer/secret zarejestrowanej aplikacji.
    Wymaga USOS_CONSUMER_KEY i USOS_CONSUMER_SECRET w .env (patrz
    .env.example).
    """
    consumer_key = os.getenv("USOS_CONSUMER_KEY")
    consumer_secret = os.getenv("USOS_CONSUMER_SECRET")
    if not consumer_key or not consumer_secret:
        raise UsosCredentialsError(
            "Brak USOS_CONSUMER_KEY/USOS_CONSUMER_SECRET w .env. Zarejestruj "
            "aplikacje na https://apps.usos.uj.edu.pl/developers/ i uzupelnij "
            ".env na podstawie .env.example."
        )

    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/" + method_path.lstrip("/")
    auth = OAuth1(consumer_key, consumer_secret)

    print(f"[request][signed] GET {url} params={params or {}}")
    response = requests.get(url, params=params or {}, auth=auth, timeout=30)

    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)

    return response.json()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_usos_api.py -v`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt src/data/usos/usos_api.py tests/data/usos/test_usos_api.py
git commit -m "Add 2-legged OAuth1-signed USOS API calls"
```

---

### Task 3: Refactor `usos_client.py` onto `usos_api.py`, add `--signed`

**Files:**
- Modify: `src/data/usos/usos_client.py`
- Test: `tests/data/usos/test_usos_client.py`

**Interfaces:**
- Consumes: `usos_api.UsosApiError`, `usos_api.UsosCredentialsError`, `usos_api.usos_call_anonymous`, `usos_api.usos_call_signed`, `usos_api.save_response`, `usos_api.RAW_DATA_DIR` (Tasks 1-2).
- Produces: `usos_client.parse_params(raw_params: list[str]) -> dict[str, str]` (unchanged signature), `usos_client.main() -> None` (now supports `--signed`).

- [ ] **Step 1: Write the failing tests**

Create `tests/data/usos/test_usos_client.py`:

```python
import sys

import pytest

import usos_api
import usos_client


def test_parse_params_parses_key_value_pairs():
    result = usos_client.parse_params(["fac_id=WMI", "lang=en"])
    assert result == {"fac_id": "WMI", "lang": "en"}


def test_parse_params_raises_on_missing_equals():
    with pytest.raises(ValueError):
        usos_client.parse_params(["not_a_pair"])


def test_main_calls_anonymous_by_default(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["usos_client.py", "services/fac/fac2", "--params", "fac_id=WMI"])
    monkeypatch.setattr(usos_client, "RAW_DATA_DIR", str(tmp_path))

    calls = {}

    def fake_anonymous(method_path, params):
        calls["method_path"] = method_path
        calls["params"] = params
        return {"ok": True}

    def fail_signed(*a, **kw):
        raise AssertionError("should not call signed without --signed")

    monkeypatch.setattr(usos_client, "usos_call_anonymous", fake_anonymous)
    monkeypatch.setattr(usos_client, "usos_call_signed", fail_signed)

    usos_client.main()

    assert calls["method_path"] == "services/fac/fac2"
    assert calls["params"] == {"fac_id": "WMI"}


def test_main_calls_signed_with_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        ["usos_client.py", "services/users/user", "--signed", "--params", "user_id=1"],
    )
    monkeypatch.setattr(usos_client, "RAW_DATA_DIR", str(tmp_path))

    calls = {}

    def fake_signed(method_path, params):
        calls["method_path"] = method_path
        calls["params"] = params
        return {"ok": True}

    def fail_anonymous(*a, **kw):
        raise AssertionError("should not call anonymous with --signed")

    monkeypatch.setattr(usos_client, "usos_call_signed", fake_signed)
    monkeypatch.setattr(usos_client, "usos_call_anonymous", fail_anonymous)

    usos_client.main()

    assert calls["method_path"] == "services/users/user"
    assert calls["params"] == {"user_id": "1"}


def test_main_exits_with_error_on_api_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["usos_client.py", "services/fac/fac2"])
    monkeypatch.setattr(usos_client, "RAW_DATA_DIR", str(tmp_path))

    def fake_anonymous(method_path, params):
        raise usos_api.UsosApiError(400, "bad request")

    monkeypatch.setattr(usos_client, "usos_call_anonymous", fake_anonymous)

    with pytest.raises(SystemExit) as exc_info:
        usos_client.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "400" in captured.err
    assert "bad request" in captured.err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_usos_client.py -v`
Expected: FAIL — `test_parse_params_*` pass (unchanged code), but the `--signed`/error-handling tests fail (`error: unrecognized arguments: --signed` / `AssertionError`), since `usos_client.py` hasn't been refactored yet.

- [ ] **Step 3: Rewrite `src/data/usos/usos_client.py`**

Replace the full contents of `src/data/usos/usos_client.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_usos_client.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full test suite so far**

Run: `pytest tests/data/usos/ -v`
Expected: PASS (14 tests total).

- [ ] **Step 6: Manually smoke-test the CLI still works end-to-end**

Run: `python src/data/usos/usos_client.py services/apisrv/now`
Expected: prints the request line, a JSON timestamp string, and a `[saved]` line pointing into `data/usos/raw/`.

- [ ] **Step 7: Commit**

```bash
git add src/data/usos/usos_client.py tests/data/usos/test_usos_client.py
git commit -m "Refactor usos_client.py onto usos_api.py, add --signed flag"
```

---

### Task 4: `scrape_staff.py` — normalization functions

**Files:**
- Create: `src/data/usos/scrape_staff.py`
- Test: `tests/data/usos/test_scrape_staff.py`

**Interfaces:**
- Produces: `scrape_staff.flatten_langdict(langdict: dict | None, preferred_lang: str = "pl") -> tuple[dict, str]`, `scrape_staff.normalize_employee(raw: dict) -> dict`, `scrape_staff.USER_FIELDS: str`, `scrape_staff.FAC_ID: str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/data/usos/test_scrape_staff.py`:

```python
import scrape_staff


def test_flatten_langdict_returns_empty_for_none():
    assert scrape_staff.flatten_langdict(None) == ({}, "")


def test_flatten_langdict_returns_empty_for_empty_dict():
    assert scrape_staff.flatten_langdict({}) == ({}, "")


def test_flatten_langdict_prefers_polish():
    langdict = {"pl": "Wtorki 10-12", "en": "Tuesdays 10-12"}
    result_dict, text = scrape_staff.flatten_langdict(langdict)
    assert result_dict == langdict
    assert text == "Wtorki 10-12"


def test_flatten_langdict_falls_back_to_other_language():
    langdict = {"en": "Tuesdays 10-12"}
    result_dict, text = scrape_staff.flatten_langdict(langdict)
    assert result_dict == langdict
    assert text == "Tuesdays 10-12"


def test_flatten_langdict_falls_back_when_polish_is_empty_string():
    langdict = {"pl": "", "en": "Tuesdays 10-12"}
    _, text = scrape_staff.flatten_langdict(langdict)
    assert text == "Tuesdays 10-12"


def test_normalize_employee_maps_all_fields():
    raw = {
        "id": 12345,
        "first_name": "Jan",
        "last_name": "Kowalski",
        "titles": {"before": "dr", "after": None},
        "email": "jan.kowalski@uj.edu.pl",
        "phone_numbers": ["123456789"],
        "room": {"id": "0.05", "number": "0.05"},
        "profile_url": "https://usosweb.uj.edu.pl/...",
        "homepage_url": None,
        "office_hours": {"pl": "Wtorki 10-12"},
        "interests": {"pl": "Uczenie maszynowe"},
        "employment_positions": [{"position": {"name": {"pl": "adiunkt"}}}],
    }

    result = scrape_staff.normalize_employee(raw)

    assert result["id"] == 12345
    assert result["first_name"] == "Jan"
    assert result["last_name"] == "Kowalski"
    assert result["titles"] == {"before": "dr", "after": None}
    assert result["email"] == "jan.kowalski@uj.edu.pl"
    assert result["phone_numbers"] == ["123456789"]
    assert result["room"] == {"id": "0.05", "number": "0.05"}
    assert result["profile_url"] == "https://usosweb.uj.edu.pl/..."
    assert result["homepage_url"] is None
    assert result["office_hours"] == {"pl": "Wtorki 10-12"}
    assert result["office_hours_text"] == "Wtorki 10-12"
    assert result["interests"] == {"pl": "Uczenie maszynowe"}
    assert result["interests_text"] == "Uczenie maszynowe"
    assert result["employment_positions"] == [{"position": {"name": {"pl": "adiunkt"}}}]


def test_normalize_employee_handles_missing_optional_fields():
    raw = {"id": 1, "first_name": "Anna", "last_name": "Nowak"}

    result = scrape_staff.normalize_employee(raw)

    assert result["phone_numbers"] == []
    assert result["employment_positions"] == []
    assert result["office_hours"] == {}
    assert result["office_hours_text"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scrape_staff'`.

- [ ] **Step 3: Create `src/data/usos/scrape_staff.py` with the normalization functions**

```python
"""
Wlasciwy scraper danych pracownikow WMI z USOS API UJ: kontakt i dyzury
("office_hours"), zapisywane jako znormalizowany dataset JSON pod katem
pozniejszego wykorzystania w RAG.
"""

from usos_api import (
    RAW_DATA_DIR,
    UsosApiError,
    save_response,
    usos_call_signed,
)

FAC_ID = "WMI"
STAFF_INDEX_PAGE_SIZE = 100
USER_FIELDS = (
    "id|first_name|last_name|titles|email|phone_numbers|office_hours|"
    "room|profile_url|homepage_url|interests|employment_positions"
)


def flatten_langdict(langdict: dict | None, preferred_lang: str = "pl") -> tuple[dict, str]:
    """Splaszcza pole typu LangDict do (oryginalny slownik, najlepszy tekst).

    Preferuje jezyk `preferred_lang`; jesli go brak lub jest pusty, bierze
    pierwsza niepusta wartosc z dostepnych jezykow. Zwraca ({}, "") dla
    pustego/brakujacego LangDict.
    """
    if not langdict:
        return {}, ""

    preferred_text = langdict.get(preferred_lang)
    if preferred_text:
        return dict(langdict), preferred_text

    for value in langdict.values():
        if value:
            return dict(langdict), value

    return dict(langdict), ""


def normalize_employee(raw: dict) -> dict:
    """Normalizuje surowa odpowiedz services/users/user do plaskiego rekordu."""
    office_hours, office_hours_text = flatten_langdict(raw.get("office_hours"))
    interests, interests_text = flatten_langdict(raw.get("interests"))

    return {
        "id": raw.get("id"),
        "first_name": raw.get("first_name"),
        "last_name": raw.get("last_name"),
        "titles": raw.get("titles"),
        "email": raw.get("email"),
        "phone_numbers": raw.get("phone_numbers") or [],
        "room": raw.get("room"),
        "profile_url": raw.get("profile_url"),
        "homepage_url": raw.get("homepage_url"),
        "office_hours": office_hours,
        "office_hours_text": office_hours_text,
        "interests": interests,
        "interests_text": interests_text,
        "employment_positions": raw.get("employment_positions") or [],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/usos/scrape_staff.py tests/data/usos/test_scrape_staff.py
git commit -m "Add employee record normalization to scrape_staff.py"
```

---

### Task 5: `scrape_staff.py` — staff ID discovery (pagination)

**Files:**
- Modify: `src/data/usos/scrape_staff.py`
- Test: `tests/data/usos/test_scrape_staff.py`

**Interfaces:**
- Consumes: `usos_api.usos_call_signed`, `usos_api.save_response`, `usos_api.RAW_DATA_DIR`, `scrape_staff.FAC_ID`, `scrape_staff.STAFF_INDEX_PAGE_SIZE` (Task 4).
- Produces: `scrape_staff.fetch_all_staff_ids(fac_id: str) -> list[int]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/usos/test_scrape_staff.py`:

```python
def test_fetch_all_staff_ids_paginates_until_next_page_false(monkeypatch):
    responses = [
        {"users": [{"id": 1}, {"id": 2}], "next_page": True, "total": 3},
        {"users": [{"id": 3}], "next_page": False, "total": 3},
    ]
    calls = []

    def fake_signed(method_path, params):
        calls.append((method_path, dict(params)))
        return responses[len(calls) - 1]

    monkeypatch.setattr(scrape_staff, "usos_call_signed", fake_signed)
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_all_staff_ids("WMI")

    assert result == [1, 2, 3]
    assert calls[0] == (
        "services/users/staff_index",
        {
            "fac_ids": "WMI",
            "fields": "users[id]|next_page|total",
            "num": "100",
            "start": "0",
        },
    )
    assert calls[1][1]["start"] == "100"


def test_fetch_all_staff_ids_single_page(monkeypatch):
    monkeypatch.setattr(
        scrape_staff,
        "usos_call_signed",
        lambda method_path, params: {"users": [{"id": 7}], "next_page": False, "total": 1},
    )
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_all_staff_ids("WMI")

    assert result == [7]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: FAIL with `AttributeError: module 'scrape_staff' has no attribute 'fetch_all_staff_ids'`.

- [ ] **Step 3: Implement `fetch_all_staff_ids`**

Add to `src/data/usos/scrape_staff.py`, after the module constants:

```python
def fetch_all_staff_ids(fac_id: str) -> list[int]:
    """Pobiera wszystkie ID pracownikow danego wydzialu, paginujac wyniki."""
    ids: list[int] = []
    start = 0

    while True:
        params = {
            "fac_ids": fac_id,
            "fields": "users[id]|next_page|total",
            "num": str(STAFF_INDEX_PAGE_SIZE),
            "start": str(start),
        }
        payload = usos_call_signed("services/users/staff_index", params)
        save_response("services/users/staff_index", payload, RAW_DATA_DIR)

        ids.extend(user["id"] for user in payload.get("users", []))

        if not payload.get("next_page"):
            break
        start += STAFF_INDEX_PAGE_SIZE

    return ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/usos/scrape_staff.py tests/data/usos/test_scrape_staff.py
git commit -m "Add staff ID discovery pagination to scrape_staff.py"
```

---

### Task 6: `scrape_staff.py` — per-employee fetch

**Files:**
- Modify: `src/data/usos/scrape_staff.py`
- Test: `tests/data/usos/test_scrape_staff.py`

**Interfaces:**
- Consumes: `usos_api.usos_call_signed`, `usos_api.save_response`, `usos_api.RAW_DATA_DIR`, `scrape_staff.USER_FIELDS` (Task 4).
- Produces: `scrape_staff.fetch_employee_detail(user_id: int) -> dict`.

- [ ] **Step 1: Write the failing test**

Append to `tests/data/usos/test_scrape_staff.py`:

```python
def test_fetch_employee_detail_calls_signed_with_correct_fields(monkeypatch):
    calls = []

    def fake_signed(method_path, params):
        calls.append((method_path, dict(params)))
        return {"id": 42, "first_name": "Ola"}

    monkeypatch.setattr(scrape_staff, "usos_call_signed", fake_signed)
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_employee_detail(42)

    assert result == {"id": 42, "first_name": "Ola"}
    assert calls == [
        ("services/users/user", {"user_id": "42", "fields": scrape_staff.USER_FIELDS})
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: FAIL with `AttributeError: module 'scrape_staff' has no attribute 'fetch_employee_detail'`.

- [ ] **Step 3: Implement `fetch_employee_detail`**

Add to `src/data/usos/scrape_staff.py`, after `fetch_all_staff_ids`:

```python
def fetch_employee_detail(user_id: int) -> dict:
    """Pobiera pelne dane jednego pracownika (services/users/user, signed)."""
    params = {"user_id": str(user_id), "fields": USER_FIELDS}
    payload = usos_call_signed("services/users/user", params)
    save_response("services/users/user", payload, RAW_DATA_DIR)
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/usos/scrape_staff.py tests/data/usos/test_scrape_staff.py
git commit -m "Add per-employee fetch to scrape_staff.py"
```

---

### Task 7: `scrape_staff.py` — save the normalized dataset

**Files:**
- Modify: `src/data/usos/scrape_staff.py`
- Test: `tests/data/usos/test_scrape_staff.py`

**Interfaces:**
- Produces: `scrape_staff.STAFF_OUTPUT_DIR: str`, `scrape_staff.save_staff_dataset(fac_id: str, employees: list[dict]) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/data/usos/test_scrape_staff.py`:

```python
import json
import os


def test_save_staff_dataset_writes_file_with_expected_name(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape_staff, "STAFF_OUTPUT_DIR", str(tmp_path))

    employees = [{"id": 1, "first_name": "Ola"}]
    path = scrape_staff.save_staff_dataset("WMI", employees)

    assert os.path.exists(path)
    assert os.path.basename(path).startswith("staff_WMI_")
    assert os.path.basename(path).endswith(".json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == employees
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: FAIL with `AttributeError: module 'scrape_staff' has no attribute 'STAFF_OUTPUT_DIR'`.

- [ ] **Step 3: Implement `save_staff_dataset`**

Add `import json`, `import os`, and `from datetime import datetime, timezone` to the top of `src/data/usos/scrape_staff.py`, and add `STAFF_OUTPUT_DIR` next to the other module constants:

```python
STAFF_OUTPUT_DIR = os.path.join("data", "usos", "staff")
```

Add the function after `fetch_employee_detail`:

```python
def save_staff_dataset(fac_id: str, employees: list[dict]) -> str:
    """Zapisuje znormalizowana liste pracownikow do jednego pliku JSON."""
    os.makedirs(STAFF_OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"staff_{fac_id}_{timestamp}.json"
    filepath = os.path.join(STAFF_OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(employees, f, ensure_ascii=False, indent=2)

    return filepath
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/usos/scrape_staff.py tests/data/usos/test_scrape_staff.py
git commit -m "Add normalized staff dataset writer to scrape_staff.py"
```

---

### Task 8: `scrape_staff.py` — orchestration with skip-on-error

**Files:**
- Modify: `src/data/usos/scrape_staff.py`
- Test: `tests/data/usos/test_scrape_staff.py`

**Interfaces:**
- Consumes: `scrape_staff.fetch_all_staff_ids`, `scrape_staff.fetch_employee_detail`, `scrape_staff.normalize_employee`, `scrape_staff.save_staff_dataset`, `usos_api.UsosApiError` (Tasks 4-7).
- Produces: `scrape_staff.run_scrape(fac_id: str = FAC_ID) -> dict` — returns `{"total_found": int, "total_fetched": int, "skipped_ids": list[int], "output_path": str}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/usos/test_scrape_staff.py`:

```python
def test_run_scrape_skips_failed_employees_and_continues(monkeypatch, capsys):
    monkeypatch.setattr(scrape_staff, "fetch_all_staff_ids", lambda fac_id: [1, 2, 3])

    def fake_fetch_detail(user_id):
        if user_id == 2:
            raise usos_api.UsosApiError(500, "server error")
        return {"id": user_id, "first_name": f"User{user_id}", "last_name": "X"}

    monkeypatch.setattr(scrape_staff, "fetch_employee_detail", fake_fetch_detail)

    saved = {}

    def fake_save(fac_id, employees):
        saved["fac_id"] = fac_id
        saved["employees"] = employees
        return "data/usos/staff/staff_WMI_fake.json"

    monkeypatch.setattr(scrape_staff, "save_staff_dataset", fake_save)

    summary = scrape_staff.run_scrape("WMI")

    assert summary["total_found"] == 3
    assert summary["total_fetched"] == 2
    assert summary["skipped_ids"] == [2]
    assert summary["output_path"] == "data/usos/staff/staff_WMI_fake.json"
    assert saved["fac_id"] == "WMI"
    assert [e["id"] for e in saved["employees"]] == [1, 3]

    captured = capsys.readouterr()
    assert "2" in captured.err
    assert "500" in captured.err
    assert "server error" in captured.err


def test_run_scrape_defaults_to_wmi(monkeypatch):
    seen_fac_ids = []
    monkeypatch.setattr(
        scrape_staff,
        "fetch_all_staff_ids",
        lambda fac_id: seen_fac_ids.append(fac_id) or [],
    )
    monkeypatch.setattr(scrape_staff, "save_staff_dataset", lambda fac_id, employees: "path")

    scrape_staff.run_scrape()

    assert seen_fac_ids == ["WMI"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: FAIL with `AttributeError: module 'scrape_staff' has no attribute 'run_scrape'`.

- [ ] **Step 3: Implement `run_scrape`**

Add `import sys` to the top of `src/data/usos/scrape_staff.py`. Add the function after `save_staff_dataset`:

```python
def run_scrape(fac_id: str = FAC_ID) -> dict:
    """Uruchamia pelny scraping: dyskonta ID, fetch kazdego, zapis datasetu.

    Bledy pojedynczych pracownikow sa logowane na stderr i pomijane - reszta
    scrapingu jest kontynuowana. Zwraca podsumowanie przebiegu.
    """
    staff_ids = fetch_all_staff_ids(fac_id)

    employees = []
    skipped_ids = []

    for user_id in staff_ids:
        try:
            raw = fetch_employee_detail(user_id)
        except UsosApiError as e:
            print(
                f"[error] Pomijam pracownika {user_id}: status {e.status_code}\n{e.body}",
                file=sys.stderr,
            )
            skipped_ids.append(user_id)
            continue

        employees.append(normalize_employee(raw))

    output_path = save_staff_dataset(fac_id, employees)

    return {
        "total_found": len(staff_ids),
        "total_fetched": len(employees),
        "skipped_ids": skipped_ids,
        "output_path": output_path,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: PASS (14 tests).

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/data/usos/ -v`
Expected: PASS (28 tests total).

- [ ] **Step 6: Commit**

```bash
git add src/data/usos/scrape_staff.py tests/data/usos/test_scrape_staff.py
git commit -m "Add run_scrape orchestration with per-employee skip-on-error"
```

---

### Task 9: `scrape_staff.py` — CLI entry point + manual end-to-end verification

**Files:**
- Modify: `src/data/usos/scrape_staff.py`

**Interfaces:**
- Consumes: `scrape_staff.run_scrape` (Task 8), `usos_api.UsosCredentialsError`, `usos_api.UsosApiError`.
- Produces: `scrape_staff.main() -> None`.

- [ ] **Step 1: Add the CLI entry point**

Add `from usos_api import UsosCredentialsError` to the existing `from usos_api import (...)` block at the top of `src/data/usos/scrape_staff.py` (so the import block reads `RAW_DATA_DIR`, `UsosApiError`, `UsosCredentialsError`, `save_response`, `usos_call_signed`).

Add at the end of `src/data/usos/scrape_staff.py`:

```python
def main() -> None:
    try:
        summary = run_scrape()
    except UsosCredentialsError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)
    except UsosApiError as e:
        print(
            f"[error] Nie udalo sie pobrac listy pracownikow: status {e.status_code}\n{e.body}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Znaleziono pracownikow: {summary['total_found']}")
    print(f"Pobrano poprawnie: {summary['total_fetched']}")
    if summary["skipped_ids"]:
        print(f"Pominieto (bledy): {summary['skipped_ids']}")
    print(f"Zapisano dataset: {summary['output_path']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full test suite one more time**

Run: `pytest tests/data/usos/ -v`
Expected: PASS (28 tests total) — `main()` itself has no new automated test (it only wires already-tested pieces together plus real stdout/stderr formatting), consistent with how `usos_client.py`'s `main()` is covered mostly through its dispatch tests.

- [ ] **Step 3: Commit**

```bash
git add src/data/usos/scrape_staff.py
git commit -m "Add scrape_staff.py CLI entry point"
```

- [ ] **Step 4: Manual end-to-end verification (requires a real USOS consumer key)**

This step cannot be automated — it needs a real registered application and hits the live USOS API. Perform it once `USOS_CONSUMER_KEY`/`USOS_CONSUMER_SECRET` are set in a local `.env` (see `.env.example`):

Run: `python src/data/usos/scrape_staff.py`

Expected:
- Console shows `[request][signed] GET ...` lines for the `staff_index` pages and each `services/users/user` call, roughly 1 second apart.
- Final summary lines: `Znaleziono pracownikow: N`, `Pobrano poprawnie: N` (or less, with a `Pominieto (bledy): [...]` line if any single employee fetch failed), `Zapisano dataset: data/usos/staff/staff_WMI_<timestamp>.json`.
- `data/usos/raw/` contains one file per `staff_index` page and one file per `services/users/user` call.
- `data/usos/staff/staff_WMI_<timestamp>.json` contains a JSON list of normalized employee records; spot-check a few entries for plausible `office_hours_text` values to confirm the assumed `LangDict` shape (`{"pl": "...", ...}`) matches what USOS actually returns — adjust `flatten_langdict`'s language-key assumption in a follow-up if it doesn't.

If this reveals that the real `office_hours`/`interests` `LangDict` shape differs from what was assumed (e.g. different language codes, or a different structure entirely), that's expected to surface only here — note it and treat it as a fast-follow fix to `flatten_langdict`, not a blocker for the rest of the plan.

---

## Self-Review Notes

- **Spec coverage:** staff discovery via `staff_index` pagination (Task 5), per-employee fetch via `services/users/user` signed calls (Task 6), `office_hours`/`interests` LangDict normalization (Task 4), raw responses to `data/usos/raw/` (Tasks 5-6, reusing existing `save_response`), normalized dataset to `data/usos/staff/` (Task 7), skip-and-continue error handling with loud logging (Task 8), whole-run abort on missing credentials or `staff_index` failure (Task 9), `requests_oauthlib` dependency (Task 2), hardcoded `fac_id=WMI` with no CLI override (Task 8/9 — `main()` takes no arguments), no `teachers_only` filtering (Task 5 — parameter is never sent). All covered.
- **Placeholder scan:** no TBD/TODO markers; every step has complete, runnable code.
- **Type consistency:** `usos_call_signed`/`usos_call_anonymous` signatures match between `usos_api.py` and their call sites in `usos_client.py` and `scrape_staff.py`. `UsosApiError`/`UsosCredentialsError` are imported and caught with matching names everywhere they're used. `fetch_employee_detail` returns the raw dict consumed by `normalize_employee`; `run_scrape` composes both plus `save_staff_dataset` with matching parameter names (`fac_id`, `employees`).
