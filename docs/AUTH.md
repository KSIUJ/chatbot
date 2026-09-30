# Logowanie przez KSI (OIDC / Keycloak)

Do chatbota logują się wyłącznie osoby z kontem KSI należące do grupy
**`/Członek`** w Keycloaku `https://auth.ksi.sh/realms/ksi`. Nie ma trybu gościa,
rejestracji ani haseł w aplikacji.

Kod: `src/backend/auth/` (backend), `src/frontend/src/features/Auth/` i
`src/frontend/src/lib/api.ts` (frontend). Testy: `tests/backend/api/test_auth.py`
(pełny przepływ przeciw atrapie Keycloaka) i `tests/backend/auth/`.

---

## 1. Jak to działa

Backend jest **klientem poufnym** (wzorzec BFF): sam wymienia kod na tokeny i sam
je przechowuje. Przeglądarka dostaje tylko ciasteczko sesji `HttpOnly` — żaden
token Keycloaka nie trafia do JavaScriptu.

```
przeglądarka ──GET /api/auth/login──▶ backend ──303──▶ auth.ksi.sh  (state, nonce, PKCE S256;
                                                                     zaszyfrowane ciasteczko logowania)
             ◀──303 /api/auth/callback?code&state──────────┘
backend: sprawdza state z ciasteczkiem → wymienia kod (client_secret + code_verifier)
       → waliduje ID token (JWKS, iss, aud, azp, exp, nonce; tylko algorytmy asymetryczne)
       → userinfo: czy /Członek jest w "groups"?  nie → ?auth_error=not_member, nic nie zapisuje
       → konto (po `sub`) + wiersz w user_sessions → ciasteczko sesji → 303 na "/"
```

**Przy każdym chronionym zapytaniu** (`/chat`, `/conversations`, `/auth/me`)
backend woła `userinfo` w Keycloaku tokenem użytkownika. Keycloak liczy grupy na
bieżąco, więc:

| co się stało w Keycloaku | skutek w chatbocie (przy najbliższym zapytaniu) |
|---|---|
| usunięcie z grupy `/Członek` | 403 `not_member`, sesja skasowana |
| wylogowanie / zablokowanie konta / koniec sesji SSO | 401 `session_expired`, sesja skasowana |
| Keycloak nie odpowiada | 503 `provider_unavailable`, sesja zostaje (fail closed) |

Access token (w KSI ważny 5 min) backend odświeża refresh tokenem. Równoległe
zapytania tej samej sesji są serializowane blokadą, żeby rotacja refresh tokenów
nie wylogowała użytkownika — blokada działa w obrębie jednego procesu, więc
backend musi chodzić na **jednym workerze** uvicorna (tak jest w `entrypoint.sh`).

Endpointy (za nginxem z prefiksem `/api`):

| endpoint | opis |
|---|---|
| `GET /auth/login` | przekierowanie do Keycloaka |
| `GET /auth/callback` | powrót z Keycloaka; błędy wracają na frontend jako `?auth_error=<kod>` |
| `GET /auth/me` | dane zalogowanego członka albo 401/403/503 z `detail.code` |
| `POST /auth/logout` | kasuje sesję, zwraca `logout_url` (wylogowanie z Keycloaka) |

Każde `POST` z nagłówkiem `Origin` spoza dozwolonych adresów dostaje 403
`forbidden_origin`. `SameSite=Lax` nie chroni przed innymi subdomenami `ksi.sh`,
bo to ta sama „site”.

---

## 2. Konfiguracja (`.env`)

Pełny opis z wartościami domyślnymi: `.env.example`, sekcja „Logowanie przez
Keycloak KSI”. Bez wymaganych zmiennych backend **nie wystartuje** i wypisze listę
braków.

| zmienna | wymagana | przykład / domyślnie |
|---|---|---|
| `OIDC_ISSUER` | tak | `https://auth.ksi.sh/realms/ksi` |
| `OIDC_CLIENT_ID` | tak | `chatbot` |
| `OIDC_CLIENT_SECRET` | tak | od adminów KSI — **nigdy w repo** |
| `OIDC_REDIRECT_URI` | tak | `https://chat.ksi.sh/api/auth/callback` |
| `AUTH_SECRET_KEY` | tak | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `OIDC_REQUIRED_GROUP` | nie | `/Członek` |
| `OIDC_GROUPS_CLAIM` | nie | `groups` |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | nie | origin z `OIDC_REDIRECT_URI` + `/` |
| `AUTH_SESSION_MAX_AGE_HOURS` | nie | `168` (sesja kończy się wcześniej razem z sesją SSO) |
| `AUTH_COOKIE_SECURE` | nie | wg schematu `OIDC_REDIRECT_URI` (https → `Secure` + prefiks `__Host-`) |
| `FRONTEND_ORIGINS` | nie | origin z `OIDC_REDIRECT_URI` jest dopuszczony automatycznie |

`OIDC_REDIRECT_URI` musi być **dokładnie** jednym z „Valid redirect URIs”
klienta w Keycloaku:

| środowisko | `OIDC_REDIRECT_URI` |
|---|---|
| Docker lokalnie | `http://localhost:8080/api/auth/callback` (port = `FRONTEND_PORT`) |
| `npm run dev` | `http://localhost:5173/api/auth/callback` |
| produkcja | `https://chat.ksi.sh/api/auth/callback` |

Zmiana `AUTH_SECRET_KEY` wylogowuje wszystkich (zapisane tokeny przestają się
odszyfrowywać) — to też sposób na awaryjne unieważnienie wszystkich sesji.

---

## 3. Wymagania po stronie Keycloaka

Klient `chatbot` w realmie `ksi`:

- Client authentication **ON**, Standard flow **ON**, PKCE **S256**.
- Service accounts, Direct access grants, Implicit — niepotrzebne (**OFF**).
- „Valid redirect URIs” i „Valid post logout redirect URIs” — adresy z tabeli wyżej.
- Mapper **Group Membership**: claim `groups`, Full group path **ON**,
  Add to userinfo **ON**. Bez niego *każde* logowanie kończy się `not_member`.
- Userinfo niepodpisane (domyślnie) — backend obsługuje tylko `application/json`.

---

## 4. Uruchomienie lokalne

**Docker:** uzupełnij w `.env` `OIDC_CLIENT_SECRET` i `AUTH_SECRET_KEY`,
`OIDC_REDIRECT_URI=http://localhost:8080/api/auth/callback`, potem
`./scripts/docker-up.sh`. Migracja bazy wykona się sama (`entrypoint.sh`).

**Bez Dockera:** `OIDC_REDIRECT_URI=http://localhost:5173/api/auth/callback`,
backend na 8000, `npm run dev` na 5173. Vite przekazuje `/api/*` do backendu
(`vite.config.ts`), więc frontend i API są na jednym originie jak w Dockerze.
Otwieraj **http://localhost:5173** (nie `127.0.0.1` — ciasteczko jest per host).

Lokalna baza `chatbot.db` założona kiedyś przez `create_all()` (bez tabeli
`alembic_version`) wymaga jednorazowo:

```bash
python -m alembic stamp d509882390a9
python -m alembic upgrade head
```

---

## 5. Wdrożenie na `chat.ksi.sh` (VM KSI, docker-compose)

Migracja `7c3e1f2a9b40` **kasuje wszystkie konta** starego systemu (rozmowy
zostają jako anonimowe). Uprzedź użytkowników — po wdrożeniu wejdą tylko członkowie
KSI.

1. Kopia bazy:
   ```bash
   docker compose run --rm --entrypoint sh backend -c "cp /app/db/chatbot.db /app/db/chatbot.db.bak-pre-oidc"
   ```
2. W `.env` na VM ustaw zmienne z rozdziału 2 (`OIDC_REDIRECT_URI=https://chat.ksi.sh/api/auth/callback`,
   nowy `AUTH_SECRET_KEY` — inny niż lokalnie).
3. `git pull && ./scripts/docker-up.sh` (przebudowa obrazów — nowe zależności).
4. Sprawdź:
   ```bash
   docker compose logs backend | grep -iE "alembic|AuthConfigError|error"
   docker compose exec backend curl -s https://auth.ksi.sh/realms/ksi/.well-known/openid-configuration | head -c 120
   curl -s https://chat.ksi.sh/api/auth/me     # {"detail":{"code":"not_authenticated",...}}
   ```
   Drugie polecenie sprawdza, czy kontener widzi Keycloaka pod publicznym adresem
   (DNS / NAT w sieci KSI).
5. Zaloguj się kontem z grupy `/Członek`, a potem przetestuj konto spoza grupy.

Reverse proxy z TLS przed nginxem frontendu musi przepuszczać ścieżki `/api/*`
bez zmian. Backend nie buduje adresów z nagłówków `Host` — wszystko jest w env.

---

## 6. Problemy

| objaw | przyczyna / co zrobić |
|---|---|
| backend nie startuje, `AuthConfigError` w logach | brakujące/błędne zmienne — komunikat wymienia wszystkie naraz |
| każdy dostaje „available to KSI members only” | brak mappera Group Membership albo `Full group path` OFF (claim ma wtedy `Członek` zamiast `/Członek`) — sprawdź `OIDC_REQUIRED_GROUP` |
| Keycloak: „Invalid parameter: redirect_uri” | `OIDC_REDIRECT_URI` nie jest w „Valid redirect URIs” klienta |
| `?auth_error=provider_unavailable` | kontener nie łączy się z `auth.ksi.sh` albo zły `OIDC_CLIENT_SECRET` (w logach: `rejected the client: invalid_client`) |
| `?auth_error=invalid_state` | logowanie trwało > 10 min albo zaczęte w innej karcie — kliknij jeszcze raz |
| po zalogowaniu wraca ekran logowania | ciasteczko `Secure` na `http://` — ustaw `OIDC_REDIRECT_URI` na właściwy schemat albo `AUTH_COOKIE_SECURE=false` lokalnie |
