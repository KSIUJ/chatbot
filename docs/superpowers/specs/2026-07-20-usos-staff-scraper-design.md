# USOS Staff Scraper — Design

**Date:** 2026-07-20
**Branch:** usos-scraping
**Status:** Approved

## Context

KSI (koło naukowe, UJ) is building a RAG system for the department. One data
source is USOS (the university's REST API) — contact info and office hours
("dyżury") for WMI (Wydział Matematyki i Informatyki) staff.

An earlier exploratory step (`src/data/usos/usos_client.py`) is a generic
anonymous CLI used to manually probe USOS API methods. This spec covers the
real scraper that replaces manual probing with an automated pipeline.

### Key findings from exploring the API (via `usos_client.py` and
`services/apiref/method`/`method_index`)

- There is **no fully-anonymous way to enumerate staff members**.
  `services/users/staff_index`, `services/users/search_staff`, and
  `services/users/search2` all require `consumer: required` (a registered
  API consumer key+secret). `services/tt/staff` is anonymous but requires an
  already-known `user_id` — so it can't be used for discovery either.
- `services/users/user` (per-employee details: `office_hours`, `phone_numbers`,
  `room`, `titles`, `employment_positions`, ...) also requires
  `consumer: required`, but `token: optional` — meaning a **2-legged**
  OAuth1 request (signed with the consumer key+secret only, no user login /
  access token) is sufficient. Fields like `office_hours` and `phone_numbers`
  are not gated behind the `personal` scope (unlike PESEL, birth date, etc.),
  so a plain consumer-signed request should return them.
- `services/fac/faculty` is fully anonymous (`consumer: optional`,
  `token: optional`) but only returns faculty-level info (address, phone,
  email of the dziekanat), not a staff list.
- `office_hours` is a free-text `LangDict` field directly on the user object
  — this is the natural "dyżury" source for RAG, as opposed to parsing
  `services/tt/staff` timetable activities (class schedule, not necessarily
  labeled as consultations).

**Conclusion:** a real staff scraper requires a registered USOS API consumer
key+secret (from `/developers/`) and 2-legged OAuth1 signing. It does **not**
require the full 3-legged (user login/redirect) flow — that stub in
`usos_client.py` (`usos_call_authenticated`) remains unimplemented and
unneeded for this feature.

## Scope

- Target faculty: `fac_id=WMI` only (not configurable at the CLI level for
  this iteration — hardcode/default, revisit if other faculties are needed
  later).
- All staff members of WMI (no `teachers_only` filter).
- Anonymous-only exploration tooling stays anonymous-only; only the new
  scraper uses the consumer-signed calls.
- Out of scope: 3-legged OAuth, incremental/delta scraping, other faculties,
  building the final `dataset/` RAG chunks (this scraper's output feeds that
  later step, but doesn't do the chunking itself).

## Architecture

Two layers, to avoid duplicating auth/rate-limit logic across scripts:

### `src/data/usos/usos_api.py` (new — shared core)

Extracted/expanded from the current `usos_client.py`:

- `usos_call_anonymous(method_path, params)` — existing unsigned GET.
- `usos_call_signed(method_path, params)` — **new**. Signs the request with
  OAuth1 using `USOS_CONSUMER_KEY`/`USOS_CONSUMER_SECRET` from `.env`, no
  access token (2-legged). Raises a clear, actionable error if the consumer
  key/secret env vars are missing (don't silently fall back to anonymous).
- `usos_call_authenticated(...)` — existing 3-legged stub, unchanged.
- `_respect_rate_limit()` / rate-limit state file — existing logic, moved
  here so both `usos_client.py` and `scrape_staff.py` share the same
  persisted 1s-minimum-gap state (a single file next to this module).
- `save_response(method_path, payload, output_dir)` — existing logic,
  parameterized so callers can choose the output directory (raw dumps vs.
  other uses).

### `src/data/usos/usos_client.py` (modified)

Becomes a thin CLI wrapper over `usos_api.py`. Same behavior as before, plus
a new `--signed` flag to manually exercise consumer-signed methods (useful
for testing the new key before running the full scraper).

### `src/data/usos/scrape_staff.py` (new — the real scraper)

CLI entry point, default `fac_id=WMI`. No required arguments for the common
case (`python scrape_staff.py`).

## Data flow

1. **Discover staff IDs.** Paginate `services/users/staff_index`
   (`fac_ids=WMI`, `fields=users[id]|next_page|total`, `num=100`), following
   `next_page`, until exhausted. Collect all staff IDs.
2. **Fetch per-employee detail.** For each ID, call `services/users/user`
   (signed) with:
   `fields=id|first_name|last_name|titles|email|phone_numbers|office_hours|room|profile_url|homepage_url|interests|employment_positions`
   — one request per employee, respecting the shared 1s rate limit.
3. **Normalize.** Flatten `office_hours` / `interests` (`LangDict`) into a
   `{lang: text}` dict, plus a convenience `office_hours_text` field that
   prefers `pl`, falling back to any other available language if `pl` is
   absent. (Exact LangDict language keys will be confirmed against real
   response data — not assumed up front.)
4. **Save raw responses.** Every API response (each `staff_index` page, each
   `user` call) is saved via `save_response` to `data/usos/raw/`, same
   convention as `usos_client.py` today.
5. **Save normalized dataset.** The full list of normalized employee dicts
   is written to `data/usos/staff/staff_WMI_<timestamp>.json`.
6. **Print a run summary** to the console: total staff found, total fetched
   successfully, count with non-empty `office_hours_text`, and the list of
   any skipped IDs (see error handling below).

## Error handling

Deliberately different from the exploratory tool's abort-on-first-error:

- **Whole-run failures** (missing consumer key/secret, `staff_index` itself
  returning non-200) abort immediately with a clear message — there's
  nothing to scrape without these.
- **Per-employee failures** (a single `services/users/user` call returning
  non-200) are logged loudly to stderr (status + body + which ID) and
  **skipped**, not retried. The run continues with the remaining IDs. Every
  skipped ID is listed again in the final summary so nothing is silently
  dropped.
- No exceptions are caught and swallowed; only the expected "non-200 HTTP
  status" case is handled specially, per the above.

## Output layout

```
data/usos/
  raw/                          # existing — every raw API response
    services_users_staff_index_<ts>.json
    services_users_user_<ts>.json
    ...
  staff/                        # new — normalized dataset
    staff_WMI_<timestamp>.json
```

## Dependencies

- New: `requests_oauthlib` (OAuth1 signing for the 2-legged consumer-signed
  requests) — added to `requirements.txt`.
- Existing: `requests`, `python-dotenv`.

## Prerequisites before running

- User must register an application at
  `https://apps.usos.uj.edu.pl/developers/` to obtain
  `USOS_CONSUMER_KEY`/`USOS_CONSUMER_SECRET`, and place them in a local
  `.env` (gitignored) following `.env.example`.
