# USOS 3-Legged OAuth (Opt-In Email Access) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement full 3-legged OAuth1 login for USOS API UJ so the scraper can optionally retrieve staff email addresses, strictly opt-in via a `--with-email` flag — never part of the default scrape.

**Architecture:** A new one-time interactive CLI (`usos_login.py`) performs the OAuth1 "request token → user authorizes in browser → PIN → access token" dance and persists the result to `.env`. `usos_api.py`'s previously-stubbed `usos_call_authenticated` becomes real, reusing a small `_get_consumer_credentials()` helper extracted from `usos_call_signed`. `scrape_staff.py` gains an opt-in `authenticated`/`with_email` parameter threaded from a new CLI flag down to the per-employee fetch. `usos_client.py` gains a matching `--authenticated` flag for manual exploration.

**Tech Stack:** Python 3.12, `requests`, `requests_oauthlib` (already a dependency), `python-dotenv`, `pytest`.

## Global Constraints

- `--with-email` (and the underlying `authenticated`/`with_email` parameters) default to `False` everywhere — this feature must never activate without the caller explicitly opting in.
- The OAuth token endpoints (`services/oauth/request_token`, `services/oauth/access_token`) return **form-encoded text**, not JSON — do not call `.json()` on their responses; parse with `urllib.parse.parse_qs`.
- Requested scopes are hardcoded to `"other_emails|offline_access"` — not a CLI-configurable value.
- `usos_login.py` never prints the actual access token or access token secret values to the console — only a success confirmation.
- `update_env_file` must preserve every existing line in `.env` (comments, `USOS_CONSUMER_KEY`, etc.) untouched, only replacing/appending the specific keys it's given.
- If `--with-email` is set but no access token exists in `.env`, the resulting `UsosCredentialsError` must abort the whole `run_scrape` run (propagate uncaught past the per-employee `except UsosApiError` skip logic) — it is a configuration error, not a per-employee data gap.
- No exceptions are silently swallowed. The only handled failure cases are "non-200 HTTP status" (`UsosApiError`) and "missing required `.env` credentials" (`UsosCredentialsError`); everything else propagates.
- No unit test hits the live USOS API or opens a real browser — every HTTP call is mocked via `unittest.mock`/`monkeypatch`; the interactive PIN-entry dance is verified manually (Task 7), not automatically.

---

## File Structure

- `src/data/usos/usos_api.py` — **modified**. New `_get_consumer_credentials()` and `_get_access_token_credentials()` helpers; `usos_call_signed` refactored to use the first; `usos_call_authenticated` implemented for real (replaces the `NotImplementedError` stub).
- `src/data/usos/usos_login.py` — **new**. One-time interactive 3-legged OAuth login CLI.
- `src/data/usos/usos_client.py` — **modified**. Adds `--authenticated` flag (mutually exclusive with `--signed`).
- `src/data/usos/scrape_staff.py` — **modified**. `fetch_employee_detail` gains an `authenticated` parameter; `run_scrape` gains `with_email`; `main()` gains `--with-email`.
- `.env.example` — **modified**. Adds `USOS_ACCESS_TOKEN`/`USOS_ACCESS_TOKEN_SECRET` placeholders.
- `tests/data/usos/test_usos_api.py` — **modified**. New tests for the two credential helpers and `usos_call_authenticated`.
- `tests/data/usos/test_usos_login.py` — **new**.
- `tests/data/usos/test_usos_client.py` — **modified**. New tests for `--authenticated`.
- `tests/data/usos/test_scrape_staff.py` — **modified**. New tests for `authenticated`/`with_email` threading.

---

### Task 1: Extract `_get_consumer_credentials()` and refactor `usos_call_signed`

**Files:**
- Modify: `src/data/usos/usos_api.py:99-127` (the `usos_call_signed` function)
- Test: `tests/data/usos/test_usos_api.py`

**Interfaces:**
- Produces: `usos_api._get_consumer_credentials() -> tuple[str, str]` (raises `UsosCredentialsError` if `USOS_CONSUMER_KEY`/`USOS_CONSUMER_SECRET` missing).
- Consumes: existing `usos_api.UsosCredentialsError` (already defined at `usos_api.py:35-36`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/usos/test_usos_api.py`:

```python
def test_get_consumer_credentials_returns_tuple(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")

    result = usos_api._get_consumer_credentials()

    assert result == ("test_key", "test_secret")


def test_get_consumer_credentials_raises_without_env(monkeypatch):
    monkeypatch.delenv("USOS_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("USOS_CONSUMER_SECRET", raising=False)

    with pytest.raises(usos_api.UsosCredentialsError):
        usos_api._get_consumer_credentials()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_usos_api.py -v`
Expected: FAIL with `AttributeError: module 'usos_api' has no attribute '_get_consumer_credentials'`.

- [ ] **Step 3: Add the helper and refactor `usos_call_signed`**

In `src/data/usos/usos_api.py`, insert this function immediately before `usos_call_signed` (i.e. right after `usos_call_anonymous`, before line 99's `def usos_call_signed`):

```python
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
```

Then replace the body of `usos_call_signed` (currently `src/data/usos/usos_api.py:99-127`) with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_usos_api.py -v`
Expected: PASS (10 tests: 8 existing + 2 new). The existing `test_usos_call_signed_raises_without_credentials` and `test_usos_call_signed_sends_oauth1_auth_and_returns_json` tests must still pass unchanged — this step is a pure refactor with no behavior change.

- [ ] **Step 5: Commit**

```bash
git add src/data/usos/usos_api.py tests/data/usos/test_usos_api.py
git commit -m "Extract _get_consumer_credentials helper from usos_call_signed"
```

---

### Task 2: Implement `usos_call_authenticated`

**Files:**
- Modify: `src/data/usos/usos_api.py:130-157` (the `usos_call_authenticated` stub)
- Test: `tests/data/usos/test_usos_api.py`

**Interfaces:**
- Consumes: `usos_api._get_consumer_credentials()` (Task 1), `usos_api.UsosApiError`, `usos_api.UsosCredentialsError`, `usos_api._respect_rate_limit`, `usos_api.BASE_URL`.
- Produces: `usos_api._get_access_token_credentials() -> tuple[str, str]` (raises `UsosCredentialsError` if `USOS_ACCESS_TOKEN`/`USOS_ACCESS_TOKEN_SECRET` missing), `usos_api.usos_call_authenticated(method_path: str, params: dict | None = None) -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/usos/test_usos_api.py`:

```python
def test_get_access_token_credentials_returns_tuple(monkeypatch):
    monkeypatch.setenv("USOS_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("USOS_ACCESS_TOKEN_SECRET", "test_token_secret")

    result = usos_api._get_access_token_credentials()

    assert result == ("test_token", "test_token_secret")


def test_get_access_token_credentials_raises_without_env(monkeypatch):
    monkeypatch.delenv("USOS_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("USOS_ACCESS_TOKEN_SECRET", raising=False)

    with pytest.raises(usos_api.UsosCredentialsError):
        usos_api._get_access_token_credentials()


def test_usos_call_authenticated_raises_without_consumer_credentials(monkeypatch):
    monkeypatch.delenv("USOS_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("USOS_CONSUMER_SECRET", raising=False)
    monkeypatch.setenv("USOS_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("USOS_ACCESS_TOKEN_SECRET", "test_token_secret")

    with pytest.raises(usos_api.UsosCredentialsError):
        usos_api.usos_call_authenticated("services/users/user", {"user_id": "1"})


def test_usos_call_authenticated_raises_without_access_token(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.delenv("USOS_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("USOS_ACCESS_TOKEN_SECRET", raising=False)

    with pytest.raises(usos_api.UsosCredentialsError):
        usos_api.usos_call_authenticated("services/users/user", {"user_id": "1"})


def test_usos_call_authenticated_sends_oauth1_auth_with_token_and_returns_json(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setenv("USOS_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("USOS_ACCESS_TOKEN_SECRET", "test_token_secret")
    monkeypatch.setattr(usos_api, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": 1, "email": "jan.kowalski@uj.edu.pl"}

    captured = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["auth"] = auth
        return FakeResponse()

    monkeypatch.setattr(usos_api.requests, "get", fake_get)

    result = usos_api.usos_call_authenticated("services/users/user", {"user_id": "1"})

    assert result == {"id": 1, "email": "jan.kowalski@uj.edu.pl"}
    assert captured["url"] == "https://apps.usos.uj.edu.pl/services/users/user"
    assert captured["params"] == {"user_id": "1"}
    assert isinstance(captured["auth"], OAuth1)
    assert captured["auth"].client.resource_owner_key == "test_token"
    assert captured["auth"].client.resource_owner_secret == "test_token_secret"


def test_usos_call_authenticated_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setenv("USOS_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("USOS_ACCESS_TOKEN_SECRET", "test_token_secret")
    monkeypatch.setattr(usos_api, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 401
        text = "invalid or expired token"

    monkeypatch.setattr(usos_api.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(usos_api.UsosApiError) as exc_info:
        usos_api.usos_call_authenticated("services/users/user", {"user_id": "1"})

    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_usos_api.py -v`
Expected: FAIL — `_get_access_token_credentials` doesn't exist, and `usos_call_authenticated` raises `NotImplementedError` instead of the expected behavior.

- [ ] **Step 3: Implement the helper and replace the stub**

In `src/data/usos/usos_api.py`, add this function immediately after `_get_consumer_credentials` (added in Task 1):

```python
def _get_access_token_credentials() -> tuple[str, str]:
    """Zwraca (access_token, access_token_secret) z .env.

    Podnosi UsosCredentialsError, jesli ktorykolwiek brakuje. Te wartosci sa
    zapisywane automatycznie przez src/data/usos/usos_login.py po przejsciu
    logowania (3-legged OAuth1).
    """
    access_token = os.getenv("USOS_ACCESS_TOKEN")
    access_token_secret = os.getenv("USOS_ACCESS_TOKEN_SECRET")
    if not access_token or not access_token_secret:
        raise UsosCredentialsError(
            "Brak USOS_ACCESS_TOKEN/USOS_ACCESS_TOKEN_SECRET w .env. Uruchom "
            "najpierw src/data/usos/usos_login.py, zeby zalogowac sie do USOS "
            "i uzyskac access token."
        )
    return access_token, access_token_secret
```

Then replace the entire `usos_call_authenticated` function (currently `src/data/usos/usos_api.py:130-157`, the `NotImplementedError` stub) with:

```python
def usos_call_authenticated(method_path: str, params: dict[str, str] | None = None) -> dict:
    """Wykonuje zapytanie GET podpisane pelnym 3-legged OAuth1.

    Podpisuje kluczem consumer ORAZ access tokenem konkretnego zalogowanego
    uzytkownika USOS - to jedyny tryb, ktory odblokowuje pola wymagajace
    scope'ow przypisanych do usera (np. email pod scope'em other_emails).
    Wymaga USOS_CONSUMER_KEY/USOS_CONSUMER_SECRET oraz USOS_ACCESS_TOKEN/
    USOS_ACCESS_TOKEN_SECRET w .env - ten drugi para zapisywana jest
    automatycznie przez src/data/usos/usos_login.py.
    """
    consumer_key, consumer_secret = _get_consumer_credentials()
    access_token, access_token_secret = _get_access_token_credentials()

    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/" + method_path.lstrip("/")
    auth = OAuth1(
        consumer_key,
        consumer_secret,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )

    print(f"[request][authenticated] GET {url} params={params or {}}")
    response = requests.get(url, params=params or {}, auth=auth, timeout=30)

    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)

    return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_usos_api.py -v`
Expected: PASS (16 tests: 10 from Task 1 + 6 new). If `captured["auth"].client.resource_owner_key` raises `AttributeError` (library internals differ from expectations), inspect `dir(captured["auth"].client)` to find the correct attribute name — `requests_oauthlib.OAuth1` wraps an `oauthlib.oauth1.Client`, which stores constructor kwargs as same-named attributes, but confirm against the installed version.

- [ ] **Step 5: Commit**

```bash
git add src/data/usos/usos_api.py tests/data/usos/test_usos_api.py
git commit -m "Implement usos_call_authenticated (3-legged OAuth1)"
```

---

### Task 3: `usos_login.py` — pure functions (parsing, URL building, .env update)

**Files:**
- Create: `src/data/usos/usos_login.py`
- Test: `tests/data/usos/test_usos_login.py`

**Interfaces:**
- Consumes: `usos_api.BASE_URL` (existing).
- Produces: `usos_login.parse_oauth_response(text: str) -> dict[str, str]`, `usos_login.build_authorize_url(oauth_token: str) -> str`, `usos_login.update_env_file(path: str, updates: dict[str, str]) -> None`, `usos_login.SCOPES: str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/data/usos/test_usos_login.py`:

```python
import usos_login


def test_parse_oauth_response_parses_form_encoded_string():
    result = usos_login.parse_oauth_response(
        "oauth_token=abc123&oauth_token_secret=xyz789&oauth_callback_confirmed=true"
    )

    assert result == {
        "oauth_token": "abc123",
        "oauth_token_secret": "xyz789",
        "oauth_callback_confirmed": "true",
    }


def test_build_authorize_url():
    url = usos_login.build_authorize_url("abc123")

    assert url == "https://apps.usos.uj.edu.pl/services/oauth/authorize?oauth_token=abc123"


def test_update_env_file_replaces_existing_lines(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "USOS_CONSUMER_KEY=abc\nUSOS_CONSUMER_SECRET=def\n", encoding="utf-8"
    )

    usos_login.update_env_file(
        str(env_path),
        {"USOS_CONSUMER_KEY": "new_key", "USOS_ACCESS_TOKEN": "tok123"},
    )

    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert "USOS_CONSUMER_KEY=new_key" in lines
    assert "USOS_CONSUMER_SECRET=def" in lines
    assert "USOS_ACCESS_TOKEN=tok123" in lines


def test_update_env_file_creates_file_if_missing(tmp_path):
    env_path = tmp_path / ".env"

    usos_login.update_env_file(str(env_path), {"USOS_ACCESS_TOKEN": "tok123"})

    assert env_path.read_text(encoding="utf-8") == "USOS_ACCESS_TOKEN=tok123\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_usos_login.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'usos_login'`.

- [ ] **Step 3: Create `src/data/usos/usos_login.py` with these three functions**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_usos_login.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/usos/usos_login.py tests/data/usos/test_usos_login.py
git commit -m "Add usos_login.py parsing/URL/env-update helpers"
```

---

### Task 4: `usos_login.py` — network functions, `main()`, and `.env.example`

**Files:**
- Modify: `src/data/usos/usos_login.py`
- Modify: `.env.example`
- Test: `tests/data/usos/test_usos_login.py`

**Interfaces:**
- Consumes: `usos_login.parse_oauth_response`, `usos_login.build_authorize_url`, `usos_login.update_env_file`, `usos_login.SCOPES` (Task 3); `usos_api.BASE_URL`, `usos_api.UsosApiError`, `usos_api._get_consumer_credentials`, `usos_api._respect_rate_limit` (existing/Task 1).
- Produces: `usos_login.get_request_token() -> tuple[str, str]`, `usos_login.exchange_for_access_token(oauth_token: str, oauth_token_secret: str, oauth_verifier: str) -> tuple[str, str]`, `usos_login.main() -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/usos/test_usos_login.py`:

```python
import pytest
from requests_oauthlib import OAuth1

import usos_api


def test_get_request_token_signs_with_oob_callback_and_scopes(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_login, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 200
        text = "oauth_token=req_tok&oauth_token_secret=req_sec&oauth_callback_confirmed=true"

    captured = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["auth"] = auth
        return FakeResponse()

    monkeypatch.setattr(usos_login.requests, "get", fake_get)

    oauth_token, oauth_token_secret = usos_login.get_request_token()

    assert oauth_token == "req_tok"
    assert oauth_token_secret == "req_sec"
    assert captured["url"] == "https://apps.usos.uj.edu.pl/services/oauth/request_token"
    assert captured["params"] == {"oauth_callback": "oob", "scopes": "other_emails|offline_access"}
    assert isinstance(captured["auth"], OAuth1)
    assert captured["auth"].client.callback_uri == "oob"


def test_get_request_token_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_login, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 401
        text = "invalid consumer"

    monkeypatch.setattr(usos_login.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(usos_api.UsosApiError) as exc_info:
        usos_login.get_request_token()

    assert exc_info.value.status_code == 401


def test_exchange_for_access_token_signs_with_verifier_and_returns_tokens(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_login, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 200
        text = "oauth_token=acc_tok&oauth_token_secret=acc_sec"

    captured = {}

    def fake_get(url, params=None, auth=None, timeout=None):
        captured["url"] = url
        captured["auth"] = auth
        return FakeResponse()

    monkeypatch.setattr(usos_login.requests, "get", fake_get)

    access_token, access_token_secret = usos_login.exchange_for_access_token(
        "req_tok", "req_sec", "1234"
    )

    assert access_token == "acc_tok"
    assert access_token_secret == "acc_sec"
    assert captured["url"] == "https://apps.usos.uj.edu.pl/services/oauth/access_token"
    assert captured["auth"].client.resource_owner_key == "req_tok"
    assert captured["auth"].client.resource_owner_secret == "req_sec"
    assert captured["auth"].client.verifier == "1234"


def test_exchange_for_access_token_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("USOS_CONSUMER_KEY", "test_key")
    monkeypatch.setenv("USOS_CONSUMER_SECRET", "test_secret")
    monkeypatch.setattr(usos_login, "_respect_rate_limit", lambda: None)

    class FakeResponse:
        status_code = 401
        text = "invalid verifier"

    monkeypatch.setattr(usos_login.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(usos_api.UsosApiError) as exc_info:
        usos_login.exchange_for_access_token("req_tok", "req_sec", "0000")

    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_usos_login.py -v`
Expected: FAIL — `usos_login` has no `requests`, `_respect_rate_limit`, `get_request_token`, or `exchange_for_access_token` yet.

- [ ] **Step 3: Add imports and the two network functions plus `main()`**

Replace the top of `src/data/usos/usos_login.py` (the `from urllib.parse import parse_qs` / `from usos_api import BASE_URL` block) with:

```python
from urllib.parse import parse_qs

import requests
from requests_oauthlib import OAuth1

from usos_api import BASE_URL, UsosApiError, _get_consumer_credentials, _respect_rate_limit
```

Then append these functions at the end of the file (after `update_env_file`):

```python
def get_request_token() -> tuple[str, str]:
    """Pobiera niezautoryzowany request token, podpisany kluczem consumer."""
    consumer_key, consumer_secret = _get_consumer_credentials()
    auth = OAuth1(consumer_key, consumer_secret, callback_uri="oob")

    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/services/oauth/request_token"
    response = requests.get(
        url, params={"oauth_callback": "oob", "scopes": SCOPES}, auth=auth, timeout=30
    )

    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)

    parsed = parse_oauth_response(response.text)
    return parsed["oauth_token"], parsed["oauth_token_secret"]


def exchange_for_access_token(
    oauth_token: str, oauth_token_secret: str, oauth_verifier: str
) -> tuple[str, str]:
    """Wymienia autoryzowany request token + PIN na docelowy access token."""
    consumer_key, consumer_secret = _get_consumer_credentials()
    auth = OAuth1(
        consumer_key,
        consumer_secret,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_token_secret,
        verifier=oauth_verifier,
    )

    _respect_rate_limit()

    url = BASE_URL.rstrip("/") + "/services/oauth/access_token"
    response = requests.get(url, auth=auth, timeout=30)

    if response.status_code != 200:
        raise UsosApiError(response.status_code, response.text)

    parsed = parse_oauth_response(response.text)
    return parsed["oauth_token"], parsed["oauth_token_secret"]


def main() -> None:
    oauth_token, oauth_token_secret = get_request_token()

    print("Otworz ten URL w przegladarce, zaloguj sie do USOS i zaakceptuj dostep:")
    print(build_authorize_url(oauth_token))
    print()
    oauth_verifier = input("Wklej tutaj PIN pokazany przez USOS: ").strip()

    access_token, access_token_secret = exchange_for_access_token(
        oauth_token, oauth_token_secret, oauth_verifier
    )

    update_env_file(
        ".env",
        {
            "USOS_ACCESS_TOKEN": access_token,
            "USOS_ACCESS_TOKEN_SECRET": access_token_secret,
        },
    )

    print("\n[ok] Zapisano USOS_ACCESS_TOKEN i USOS_ACCESS_TOKEN_SECRET do .env.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_usos_login.py -v`
Expected: PASS (8 tests: 4 from Task 3 + 4 new). If `captured["auth"].client.callback_uri`/`resource_owner_key`/`verifier` raise `AttributeError`, inspect `dir(captured["auth"].client)` to find the right attribute path for the installed `requests_oauthlib`/`oauthlib` version.

- [ ] **Step 5: Update `.env.example`**

Replace the full contents of `.env.example` with:

```
# USOS API UJ - dane aplikacji zarejestrowanej na https://apps.usos.uj.edu.pl/developers/
# Potrzebne dla wywolan podpisanych kluczem consumer (2-legged OAuth1, bez
# logowania uzytkownika) - patrz usos_call_signed() w src/data/usos/usos_api.py,
# uzywane przez scrape_staff.py oraz usos_client.py --signed. Tryb anonimowy
# (domyslny w usos_client.py) tego NIE wymaga. Pelny 3-legged flow
# (usos_call_authenticated() w usos_api.py) nie jest jeszcze zaimplementowany
# i tez skorzystalby z tych samych kluczy.
USOS_CONSUMER_KEY=
USOS_CONSUMER_SECRET=

# Wypelniane automatycznie przez src/data/usos/usos_login.py po przejsciu
# jednorazowego logowania 3-legged OAuth1 - NIE wpisuj tu nic recznie.
# Wymagane przez usos_call_authenticated() i flage --with-email w
# scrape_staff.py.
USOS_ACCESS_TOKEN=
USOS_ACCESS_TOKEN_SECRET=
```

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/data/usos/ -v`
Expected: PASS (all tests across all files: 16 in `test_usos_api.py`, 8 in `test_usos_login.py`, plus the unchanged `test_usos_client.py` (5) and `test_scrape_staff.py` (13) counts — 42 total).

- [ ] **Step 7: Commit**

```bash
git add src/data/usos/usos_login.py .env.example tests/data/usos/test_usos_login.py
git commit -m "Add usos_login.py network functions and CLI entry point"
```

---

### Task 5: `usos_client.py` — add `--authenticated` flag

**Files:**
- Modify: `src/data/usos/usos_client.py`
- Test: `tests/data/usos/test_usos_client.py`

**Interfaces:**
- Consumes: `usos_api.usos_call_authenticated` (Task 2).
- Produces: no new public function — `usos_client.main()`'s behavior extends to dispatch on `--authenticated`.

- [ ] **Step 1: Write the failing test**

Append to `tests/data/usos/test_usos_client.py`:

```python
def test_main_calls_authenticated_with_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        ["usos_client.py", "services/users/user", "--authenticated", "--params", "user_id=1"],
    )
    monkeypatch.setattr(usos_client, "RAW_DATA_DIR", str(tmp_path))

    calls = {}

    def fake_authenticated(method_path, params):
        calls["method_path"] = method_path
        calls["params"] = params
        return {"ok": True}

    def fail_signed(*a, **kw):
        raise AssertionError("should not call signed with --authenticated")

    def fail_anonymous(*a, **kw):
        raise AssertionError("should not call anonymous with --authenticated")

    monkeypatch.setattr(usos_client, "usos_call_authenticated", fake_authenticated)
    monkeypatch.setattr(usos_client, "usos_call_signed", fail_signed)
    monkeypatch.setattr(usos_client, "usos_call_anonymous", fail_anonymous)

    usos_client.main()

    assert calls["method_path"] == "services/users/user"
    assert calls["params"] == {"user_id": "1"}


def test_main_rejects_both_signed_and_authenticated(monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["usos_client.py", "services/users/user", "--signed", "--authenticated"]
    )

    with pytest.raises(SystemExit) as exc_info:
        usos_client.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "not allowed" in captured.err or "niedozwolone" in captured.err.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_usos_client.py -v`
Expected: FAIL — `error: unrecognized arguments: --authenticated`.

- [ ] **Step 3: Add the flag and dispatch logic**

In `src/data/usos/usos_client.py`, change the import block (currently lines 18-25) to:

```python
from usos_api import (
    RAW_DATA_DIR,
    UsosApiError,
    UsosCredentialsError,
    save_response,
    usos_call_anonymous,
    usos_call_authenticated,
    usos_call_signed,
)
```

Replace the `parser.add_argument("--signed", ...)` block (currently lines 56-60) and everything through the end of `main()`'s error handling (through line 80) with:

```python
    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument(
        "--signed",
        action="store_true",
        help="Podpisz zapytanie kluczem consumer (2-legged OAuth1), wymaga .env",
    )
    auth_group.add_argument(
        "--authenticated",
        action="store_true",
        help="Podpisz zapytanie pelnym 3-legged OAuth1 (consumer + access token), "
        "wymaga uruchomienia usos_login.py wczesniej",
    )
    args = parser.parse_args()

    try:
        params = parse_params(args.params)
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.authenticated:
            payload = usos_call_authenticated(args.method_path, params)
        elif args.signed:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_usos_client.py -v`
Expected: PASS (7 tests: 5 existing + 2 new). `argparse`'s mutually-exclusive group produces its own `SystemExit(2)` with an "not allowed with argument" message on stderr when both flags are passed — no custom handling needed for that case.

- [ ] **Step 5: Commit**

```bash
git add src/data/usos/usos_client.py tests/data/usos/test_usos_client.py
git commit -m "Add --authenticated flag to usos_client.py"
```

---

### Task 6: `scrape_staff.py` — opt-in `--with-email`

**Files:**
- Modify: `src/data/usos/scrape_staff.py`
- Test: `tests/data/usos/test_scrape_staff.py`

**Interfaces:**
- Consumes: `usos_api.usos_call_authenticated` (Task 2).
- Produces: `scrape_staff.fetch_employee_detail(user_id: int, authenticated: bool = False) -> dict` (signature change — `authenticated` is new, defaults `False`), `scrape_staff.run_scrape(fac_id: str = FAC_ID, with_email: bool = False) -> dict` (signature change — `with_email` is new, defaults `False`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/usos/test_scrape_staff.py`:

```python
def test_fetch_employee_detail_uses_signed_by_default(monkeypatch):
    calls = {"signed": 0, "authenticated": 0}

    monkeypatch.setattr(
        scrape_staff, "usos_call_signed", lambda *a, **kw: calls.__setitem__("signed", calls["signed"] + 1) or {"id": 1}
    )
    monkeypatch.setattr(
        scrape_staff,
        "usos_call_authenticated",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not call authenticated by default")),
    )
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_employee_detail(1)

    assert result == {"id": 1}
    assert calls["signed"] == 1


def test_fetch_employee_detail_uses_authenticated_when_requested(monkeypatch):
    calls = []

    def fake_authenticated(method_path, params):
        calls.append((method_path, dict(params)))
        return {"id": 1, "email": "jan.kowalski@uj.edu.pl"}

    def fail_signed(*a, **kw):
        raise AssertionError("should not call signed when authenticated=True")

    monkeypatch.setattr(scrape_staff, "usos_call_authenticated", fake_authenticated)
    monkeypatch.setattr(scrape_staff, "usos_call_signed", fail_signed)
    monkeypatch.setattr(scrape_staff, "save_response", lambda *a, **kw: "irrelevant")

    result = scrape_staff.fetch_employee_detail(1, authenticated=True)

    assert result == {"id": 1, "email": "jan.kowalski@uj.edu.pl"}
    assert calls == [("services/users/user", {"user_id": "1", "fields": scrape_staff.USER_FIELDS})]


def test_run_scrape_threads_with_email_to_fetch_employee_detail(monkeypatch):
    monkeypatch.setattr(scrape_staff, "fetch_all_staff_ids", lambda fac_id: [1, 2])

    calls = []

    def fake_fetch_detail(user_id, authenticated=False):
        calls.append((user_id, authenticated))
        return {"id": user_id, "first_name": "X", "last_name": "Y"}

    monkeypatch.setattr(scrape_staff, "fetch_employee_detail", fake_fetch_detail)
    monkeypatch.setattr(scrape_staff, "save_staff_dataset", lambda fac_id, employees: "path")

    scrape_staff.run_scrape("WMI", with_email=True)

    assert calls == [(1, True), (2, True)]


def test_run_scrape_defaults_with_email_to_false(monkeypatch):
    monkeypatch.setattr(scrape_staff, "fetch_all_staff_ids", lambda fac_id: [1])

    calls = []

    def fake_fetch_detail(user_id, authenticated=False):
        calls.append(authenticated)
        return {"id": user_id, "first_name": "X", "last_name": "Y"}

    monkeypatch.setattr(scrape_staff, "fetch_employee_detail", fake_fetch_detail)
    monkeypatch.setattr(scrape_staff, "save_staff_dataset", lambda fac_id, employees: "path")

    scrape_staff.run_scrape("WMI")

    assert calls == [False]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: FAIL — `fetch_employee_detail() got an unexpected keyword argument 'authenticated'` / `run_scrape() got an unexpected keyword argument 'with_email'` / `AttributeError: module 'scrape_staff' has no attribute 'usos_call_authenticated'`.

- [ ] **Step 3: Update `scrape_staff.py`**

Change the `from usos_api import (...)` block (currently `src/data/usos/scrape_staff.py:12-18`) to:

```python
from usos_api import (
    RAW_DATA_DIR,
    UsosApiError,
    UsosCredentialsError,
    save_response,
    usos_call_authenticated,
    usos_call_signed,
)
```

Replace `fetch_employee_detail` (currently `src/data/usos/scrape_staff.py:53-58`) with:

```python
def fetch_employee_detail(user_id: int, authenticated: bool = False) -> dict:
    """Pobiera pelne dane jednego pracownika (services/users/user).

    Domyslnie uzywa 2-legged (usos_call_signed). Gdy authenticated=True,
    uzywa pelnego 3-legged OAuth1 (usos_call_authenticated) - jedyny tryb, w
    ktorym pole 'email' (juz obecne w USER_FIELDS) faktycznie sie wypelnia.
    """
    params = {"user_id": str(user_id), "fields": USER_FIELDS}
    if authenticated:
        payload = usos_call_authenticated("services/users/user", params)
    else:
        payload = usos_call_signed("services/users/user", params)
    save_response("services/users/user", payload, RAW_DATA_DIR)
    return payload
```

Replace `run_scrape` (currently `src/data/usos/scrape_staff.py:75-106`) with:

```python
def run_scrape(fac_id: str = FAC_ID, with_email: bool = False) -> dict:
    """Uruchamia pelny scraping: dyskonta ID, fetch kazdego, zapis datasetu.

    Bledy pojedynczych pracownikow sa logowane na stderr i pomijane - reszta
    scrapingu jest kontynuowana. with_email=True dolacza email (wymaga
    wczesniejszego logowania przez usos_login.py) - jesli brak access
    tokena, blad podnosi sie na pierwszym pracowniku i przerywa caly
    przebieg (to blad konfiguracji, nie pojedynczego rekordu). Zwraca
    podsumowanie przebiegu.
    """
    staff_ids = fetch_all_staff_ids(fac_id)

    employees = []
    skipped_ids = []

    for user_id in staff_ids:
        try:
            raw = fetch_employee_detail(user_id, authenticated=with_email)
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

Replace `main()` (currently `src/data/usos/scrape_staff.py:153-170`) with:

```python
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scraper danych pracownikow WMI z USOS API UJ."
    )
    parser.add_argument(
        "--with-email",
        action="store_true",
        help="Pobierz tez email (wymaga wczesniejszego logowania przez "
        "usos_login.py) - domyslnie WYLACZONE",
    )
    args = parser.parse_args()

    try:
        summary = run_scrape(with_email=args.with_email)
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
```

Add `import argparse` to the top of the file, alongside the existing `import json`, `import os`, `import sys` (currently `src/data/usos/scrape_staff.py:7-9`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/usos/test_scrape_staff.py -v`
Expected: PASS (all existing tests plus the 4 new ones — existing tests that call `fetch_employee_detail(user_id)` or `run_scrape("WMI")` positionally/without the new kwargs must still pass unchanged, since both new parameters default to `False`).

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/data/usos/ -v`
Expected: PASS, no regressions across any of the four test files.

- [ ] **Step 6: Commit**

```bash
git add src/data/usos/scrape_staff.py tests/data/usos/test_scrape_staff.py
git commit -m "Add opt-in --with-email flag to scrape_staff.py"
```

---

### Task 7: Manual end-to-end verification (real login + `--with-email` run)

**Files:** none (verification only — no code changes in this task).

This task cannot be automated: it requires a real interactive browser login as a real USOS user, and hits the live USOS API. Perform it only when you're ready to actually exercise the 3-legged flow (per the earlier discussion about consequences of scraping with your own account) — this task is about confirming the *mechanism* works, not about running a full 208-person email harvest.

- [ ] **Step 1: Run the login flow**

Run: `python src/data/usos/usos_login.py`

Expected: prints the authorize URL, waits for a PIN via `input()`. Open the URL in a browser, log into USOS, approve the app, copy the PIN shown, paste it in. Script should print `[ok] Zapisano USOS_ACCESS_TOKEN i USOS_ACCESS_TOKEN_SECRET do .env.` without ever printing the token values themselves.

- [ ] **Step 2: Confirm `.env` was updated correctly**

Run: `grep -c "USOS_ACCESS_TOKEN" .env` (or open `.env` and check manually) — confirm both `USOS_ACCESS_TOKEN=` and `USOS_ACCESS_TOKEN_SECRET=` now have non-empty values, and `USOS_CONSUMER_KEY`/`USOS_CONSUMER_SECRET` are unchanged.

- [ ] **Step 3: Test a single authenticated call manually**

Run: `python src/data/usos/usos_client.py services/users/user --authenticated --params user_id=<your own USOS numeric ID>`

(Use your own ID here, not a bulk fetch — the point is to confirm the mechanism works, not to harvest data yet.) Expected: JSON response with your own `email` field populated (non-null), since reading your own email only requires the `email` scope on your own account, which any logged-in access token has implicitly for its own owner regardless of granted scopes for *other* users.

- [ ] **Step 4: Confirm `--with-email` is still opt-in on the full scraper**

Run: `python src/data/usos/scrape_staff.py` (no flag) — confirm behavior is unchanged from before this feature (no `[request][authenticated]` lines in the output, `email` still null in the resulting dataset). This confirms the opt-in default held through all the changes in this plan.

- [ ] **Step 5: Report back and decide on bulk usage separately**

Do not run `scrape_staff.py --with-email` against the full WMI staff list as part of this task — that decision (whether/when to actually harvest ~200 people's emails with a personal account) was explicitly deferred to a separate conversation with whoever advises the KSI project, per the consequences discussion. This task only confirms the technical mechanism is correct and remains opt-in.

---

## Self-Review Notes

- **Spec coverage:** `_get_consumer_credentials`/`_get_access_token_credentials` helpers (Tasks 1-2), `usos_call_authenticated` implementation (Task 2), form-encoded OAuth response parsing (Task 3), oob/PIN request-token → authorize → access-token flow (Task 4), `.env` persistence without echoing secrets (Tasks 3-4), `--authenticated` on `usos_client.py` (Task 5), opt-in `--with-email` on `scrape_staff.py` with whole-run-abort-on-missing-token semantics (Task 6), manual verification without a full bulk run (Task 7). All spec sections covered.
- **Placeholder scan:** no TBD/TODO markers; every step has complete, runnable code.
- **Type consistency:** `fetch_employee_detail(user_id: int, authenticated: bool = False)` and `run_scrape(fac_id: str = FAC_ID, with_email: bool = False)` signatures match between their definitions (Task 6) and every call site introduced across the tasks. `usos_call_authenticated(method_path: str, params: dict | None = None) -> dict` matches the shape of the existing `usos_call_signed`, and both `usos_client.py` (Task 5) and `scrape_staff.py` (Task 6) import and call it with that exact signature. `UsosCredentialsError`/`UsosApiError` are the same two exception classes used consistently across every task that raises or catches them.
