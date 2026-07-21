# USOS 3-Legged OAuth (Authenticated Email Access) — Design

**Date:** 2026-07-21
**Branch:** usos-scraping
**Status:** Approved

## Context

The USOS staff scraper (`scrape_staff.py`) currently uses 2-legged OAuth1
(`usos_call_signed` in `usos_api.py`) to fetch WMI staff records. A live run
against 208 real staff members confirmed that `email` is *always* null under
2-legged auth — per `services/users/user`'s own field docs, `email` requires
the `email` (own) or `other_emails` (others') scope, both of which only
exist on a real user access token. 2-legged calls are treated by USOS as an
anonymous external caller, which structurally cannot see emails regardless
of consumer permissions.

This spec covers implementing the previously-stubbed `usos_call_authenticated`
(3-legged OAuth1: consumer key/secret + a real USOS user's access
token/secret) so email can optionally be retrieved — **strictly opt-in**,
not part of the default scrape, given the real privacy/policy weight of
authenticating as a personal USOS account to harvest personal data (emails)
about ~200 other people and store it outside USOS. That weighing was
discussed explicitly with the user; this spec covers only the technical
mechanism, which the user can choose when (and whether) to actually invoke
with `--with-email`.

### Key findings from exploring the OAuth endpoints

- `services/oauth/request_token`, `services/oauth/authorize`,
  `services/oauth/access_token` implement standard OAuth 1.0a's
  three-step dance. USOS supports the "oob" (out-of-band) `oauth_callback`
  value, which avoids needing a local redirect/callback HTTP server — the
  user is shown a PIN code (`oauth_verifier`) on a USOS web page after
  logging in and approving, and types it into the CLI.
- **`request_token` and `access_token` return form-encoded text**
  (`oauth_token=...&oauth_token_secret=...[&oauth_callback_confirmed=true]`),
  *not* JSON like every other USOS API method used so far. These two
  endpoints have no `format` argument at all — this is a hard protocol
  difference from `usos_call_anonymous`/`usos_call_signed`, which both call
  `.json()` on the response.
- `services/apiref/scopes` lists all valid scope keys. The two relevant
  ones: `other_emails` ("access to email addresses of other users") and
  `offline_access` ("makes Access Tokens long-lived" — without it, tokens
  expire quickly per USOS's default session-bound lifetime).
- Once granted, an access token authorizes *every* scope the user has ever
  granted the app across all past authorizations, not just the scopes
  requested in the current `request_token` call.

## Scope

- New one-time interactive login script (`usos_login.py`) that performs the
  full 3-legged dance and persists the resulting access token/secret to
  `.env`.
- `usos_call_authenticated` in `usos_api.py` implemented for real (was a
  `NotImplementedError` stub).
- `scrape_staff.py` gets an opt-in `--with-email` flag; default behavior
  (no flag) is unchanged from the existing 2-legged scrape.
- `usos_client.py` gets a `--authenticated` flag for manual exploratory
  testing, mirroring the existing `--signed` flag.
- Out of scope: automatic token refresh/expiry handling beyond what
  `offline_access` already provides; multi-user token management (this is a
  single developer's personal token, not a multi-tenant system); wiring
  `--with-email` into any default/automatic invocation.

## Architecture

### `src/data/usos/usos_api.py` (modified)

- **New:** `_get_consumer_credentials() -> tuple[str, str]` — extracts the
  existing consumer-key/secret-missing check out of `usos_call_signed` into
  a small reusable helper (raises `UsosCredentialsError` on missing keys).
  Reused by `usos_call_signed`, the new `usos_call_authenticated`, and
  `usos_login.py`. This is the one DRY change in scope — motivated directly
  by `usos_login.py` needing the identical check, not a broader refactor.
- **New:** `usos_call_authenticated(method_path, params=None) -> dict` —
  same shape as `usos_call_signed`: rate-limited, prints a
  `[request][authenticated]` line, raises `UsosApiError` on non-200,
  returns parsed JSON (this endpoint *is* a normal JSON-returning API
  method, unlike the OAuth token endpoints). Additionally reads
  `USOS_ACCESS_TOKEN`/`USOS_ACCESS_TOKEN_SECRET` from the environment; if
  either is missing, raises `UsosCredentialsError` with a message pointing
  at running `usos_login.py`. Signs with
  `OAuth1(consumer_key, consumer_secret, resource_owner_key=access_token, resource_owner_secret=access_token_secret)`.

### `src/data/usos/usos_login.py` (new)

One-time interactive CLI, not part of the automated test suite's happy path
(the live browser/PIN dance can't be meaningfully mocked end-to-end — see
Testing below). Composed of small testable pieces:

- `parse_oauth_response(text: str) -> dict[str, str]` — parses a
  form-encoded OAuth response body (`urllib.parse.parse_qs`, single value
  per key) into a plain dict.
- `get_request_token() -> tuple[str, str]` — signs a GET to
  `services/oauth/request_token` with `oauth_callback=oob`,
  `scopes=other_emails|offline_access` (hardcoded constant, not a CLI
  flag — YAGNI, matches `FAC_ID` being hardcoded in `scrape_staff.py`).
  Returns `(oauth_token, oauth_token_secret)` via `parse_oauth_response`.
- `build_authorize_url(oauth_token: str) -> str` — returns
  `f"{BASE_URL}services/oauth/authorize?oauth_token={oauth_token}"`.
- `exchange_for_access_token(oauth_token, oauth_token_secret, oauth_verifier) -> tuple[str, str]`
  — signs a GET to `services/oauth/access_token` with
  `OAuth1(consumer_key, consumer_secret, resource_owner_key=oauth_token, resource_owner_secret=oauth_token_secret, verifier=oauth_verifier)`.
  Returns `(access_token, access_token_secret)` via `parse_oauth_response`.
- `update_env_file(path: str, updates: dict[str, str]) -> None` — reads the
  file's existing lines; for each `key` in `updates`, replaces the first
  line starting with `key=` in place, or appends `key=value` if no such
  line exists. Preserves every other line (including `USOS_CONSUMER_KEY`,
  comments, blank lines) untouched.
- `main()` — orchestrates: `get_request_token()` → print the authorize URL
  and instructions → `input("PIN: ")` → `exchange_for_access_token(...)` →
  `update_env_file(".env", {...})` → print a success confirmation **without
  ever printing the actual token or secret values** to the console.

### `src/data/usos/scrape_staff.py` (modified)

- `fetch_employee_detail(user_id: int, authenticated: bool = False) -> dict`
  — calls `usos_call_authenticated` instead of `usos_call_signed` when
  `authenticated=True`. Same `USER_FIELDS`, same `save_response` call — the
  only thing that changes is which auth mode signs the request, since
  `email` is already part of `USER_FIELDS` and simply stops being null once
  the caller has a valid `other_emails`-scoped access token.
- `run_scrape(fac_id: str = FAC_ID, with_email: bool = False) -> dict` —
  threads `with_email` through to each `fetch_employee_detail(user_id, authenticated=with_email)`
  call. `fetch_all_staff_ids` is unchanged (staff-index discovery only ever
  needs 2-legged access, regardless of `with_email`).
- `main()` — adds a `--with-email` `argparse` flag (default `False`), passed
  through to `run_scrape`.
- **Error-handling note:** if `--with-email` is set but no access token
  exists, `usos_call_authenticated` raises `UsosCredentialsError` on the
  *first* employee fetch. This is **not** caught by the existing
  `except UsosApiError` per-employee skip logic (different exception
  class), so it propagates out of `run_scrape` and aborts the whole run —
  which is correct: a missing token is a configuration problem, not a
  per-employee data gap, and should fail loudly once rather than skip all
  208 employees individually with 208 repeated error lines.

### `src/data/usos/usos_client.py` (modified)

- Adds `--authenticated` (in an `argparse` mutually-exclusive group with
  the existing `--signed`, since specifying both is meaningless) for manual
  testing of authenticated calls — mirrors the existing `--signed` pattern
  from the earlier design.

### `.env.example` (modified)

- Adds `USOS_ACCESS_TOKEN=` / `USOS_ACCESS_TOKEN_SECRET=` placeholders with
  a comment noting these are populated by running `usos_login.py`, not
  filled in by hand.

## Data flow (login)

1. User runs `python src/data/usos/usos_login.py`.
2. Script requests a request token (2-legged, consumer-only signing),
   printing the authorize URL.
3. User opens the URL in a browser, logs into USOS, approves the app, and
   is shown a PIN.
4. User types the PIN into the running script.
5. Script exchanges the request token + PIN for an access token/secret via
   a second 2-legged-signed call (signed with consumer key/secret AND the
   *request* token/secret — standard OAuth1 token-exchange signing).
6. Script writes both values into `.env` and confirms success without
   echoing them.

## Testing

- `parse_oauth_response`, `build_authorize_url`, `update_env_file`: pure
  functions, fully unit-tested with real string/file inputs (the last via
  `tmp_path`), no mocking needed beyond the file itself.
- `get_request_token`, `exchange_for_access_token`: unit-tested via mocked
  `requests.get` returning canned form-encoded response text, asserting the
  correct OAuth1 signing parameters were used and the response was parsed
  correctly.
- `usos_call_authenticated`: unit-tested the same way as `usos_call_signed`
  was (missing-credentials paths for both consumer and access-token cases,
  successful call with correct `OAuth1` params, non-200 raises
  `UsosApiError`) — all via mocked `requests.get`.
- `fetch_employee_detail`'s `authenticated` dispatch and `run_scrape`'s
  `with_email` threading: unit-tested via mocking `usos_call_authenticated`
  vs `usos_call_signed` and asserting which one gets called.
- `usos_login.py`'s `main()` (the actual browser/PIN interactive dance) is
  **not** automatically tested — same rationale as `scrape_staff.py`'s
  `main()` in the previous feature: it requires a live browser action and
  human PIN entry. Covered by a manual verification step instead, run once
  credentials exist, with real login).
- Manual verification also covers running `scrape_staff.py --with-email`
  end-to-end afterward and confirming `email` is now populated for at least
  one record, without committing or printing personal data.
