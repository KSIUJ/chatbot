<h1 align="center">Chatbot WMiI UJ</h1>

<p align="center">
  Chatbot RAG odpowiadający na pytania studentów i kandydatów o Wydział Matematyki i Informatyki UJ.
  <br>Projekt Koła Studentów Informatyki (KSI).
</p>

<p align="center"><b>Polski</b> · <a href="README.en.md">English</a></p>

---

## Spis treści

- [Jak to działa](#jak-to-działa)
- [Struktura repozytorium](#struktura-repozytorium)
- [Uruchomienie przez Docker](#uruchomienie-przez-docker)
- [Praca lokalna bez Dockera](#praca-lokalna-bez-dockera)
- [Dane: scraping i ingest](#dane-scraping-i-ingest)
- [Logowanie (OIDC, Keycloak KSI)](#logowanie-oidc-keycloak-ksi)
- [Historia rozmów](#historia-rozmów)
- [Zespół](#zespół)

## Jak to działa

- **Frontend** (React) wysyła pytanie do **backendu** (FastAPI).
- Backend wyszukuje kontekst **hybrydowo**: wyszukiwanie wektorowe (Chroma, embeddingi `sdadas/mmlw-roberta-large`) + indeks leksykalny SQLite FTS5 + wyszukiwanie pracowników po nazwisku (dane z USOS).
- Źródła danych: strony wydziałowe (`strony`), pracownicy z USOS API (`usos`), materiały studenckie z Mordoru (`mordor`).
- Odpowiedź generuje LLM wybrany przez `LLM_PROVIDER`: `ollama` (domyślnie, lokalny model `qwen2.5:14b`), `claude`, `openrouter` albo `cursor`.
- Dostęp mają tylko członkowie KSI (logowanie przez Keycloak KSI). Konta, sesje i rozmowy są w bazie SQLite `chatbot.db`.

## Struktura repozytorium

```
src/backend/          FastAPI: main.py (/chat, /conversations, /auth/*, /api/stats, /health)
  auth/               logowanie OIDC przez Keycloak KSI
  history.py          limity i czas przechowywania historii rozmów
  llm/                dostawcy LLM (ollama, claude, openrouter, cursor), http_api.py - wspólny helper
  rag/                retrieval: encoder, vectorstore (Chroma), lexical (FTS5), staff, context_builder, schema
src/frontend/         React 19 + Vite + Tailwind 4 + TypeScript, nginx.conf dla obrazu Dockera
pipeline/
  scrapers/           mordor, strony, usos - pobieranie danych do data/<źródło>/
  ingest/             ładowanie data/ do indeksu RAG w dataset/
alembic/              migracje bazy aplikacji (SQLite chatbot.db)
tests/backend/        testy pytest
scripts/              docker-up.sh, docker-seed-data.sh
data/                 surowe dane ze scraperów (poza gitem)
dataset/              indeks RAG: vectorstore/ (Chroma) i lexical.db (FTS5) (poza gitem)
```

## Uruchomienie przez Docker

Wymagania: Docker z Compose v2 (`docker compose`). GPU NVIDIA jest opcjonalne. Skrypty `scripts/*.sh` na Windowsie uruchamiaj w Git Bash.

### 1. Konfiguracja

```bash
cp .env.example .env
```

W `.env` uzupełnij co najmniej:

- `OIDC_CLIENT_SECRET` (od adminów KSI) i `AUTH_SECRET_KEY` (min. 32 znaki):
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- `OIDC_REDIRECT_URI` — domyślnie `http://localhost:8080/api/auth/callback` (port = `FRONTEND_PORT`).
- Klucz API wybranego dostawcy, jeśli `LLM_PROVIDER` to nie `ollama`: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` albo `CURSOR_API_KEY`.

Bez wymaganych zmiennych logowania backend nie wystartuje (w logach `AuthConfigError` z listą braków). Pozostałe zmienne są opisane w `.env.example`.

### 2. Start

```bash
./scripts/docker-up.sh                 # backend + frontend (LLM przez API)
./scripts/docker-up.sh --ollama        # + lokalna Ollama (potrzebne przy LLM_PROVIDER=ollama)
./scripts/docker-up.sh --ollama --gpu  # + GPU NVIDIA (wymaga NVIDIA Container Toolkit)
```

Skrypt tworzy `.env` z `.env.example`, jeśli go nie ma, i uruchamia `docker compose ... up -d --build`. Ręczne odpowiedniki:

```bash
docker compose up -d --build
docker compose --profile ollama up -d --build
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d --build
```

- Ollama jest w profilu `ollama` i bez niego nie startuje. Przy pierwszym uruchomieniu `ollama-pull` pobiera model `OLLAMA_MODEL` (domyślnie `qwen2.5:14b`, kilka GB) do wolumenu `ollama-data`.
- `docker-compose.gpu.yml` dodaje rezerwację GPU dla `ollama` i `backend` (`RAG_DEVICE=cuda`). Bez karty NVIDIA stos z tym plikiem nie wystartuje.
- Frontend: **http://localhost:8080** (`FRONTEND_PORT`). Backend bezpośrednio: http://localhost:8000/health. Oba porty są wystawione tylko na `127.0.0.1`.
- nginx we frontendzie przekazuje `/api/*` do backendu, obcinając prefiks `/api` (np. `/api/auth/me` → `/auth/me`).
- Backend przy starcie wykonuje `alembic upgrade head`, potem uruchamia uvicorn (`docker/entrypoint.sh`).

### 3. Dane RAG

Świeże wolumeny `chatbot-data` i `chatbot-dataset` są puste — chatbot odpowiada, ale nic nie wie o wydziale. Dane trafiają do nich tak:

```bash
# kopiuje lokalne data/ i dataset/ do wolumenów i restartuje backend
./scripts/docker-seed-data.sh

# jeśli skopiowałeś tylko surowe data/ - zbuduj indeks w kontenerze
docker compose exec backend python -m pipeline.ingest.run_ingest
docker compose restart backend
```

Scrapery nie są częścią obrazu — uruchamia się je lokalnie (zob. [Dane](#dane-scraping-i-ingest)).

### 4. Przydatne polecenia

```bash
docker compose ps                    # status i healthchecki
docker compose logs -f backend       # logi backendu
docker compose exec backend sh       # powłoka w kontenerze
docker compose up -d                 # po zmianie .env (odtwarza zmienione kontenery)
docker compose up -d --build         # po zmianie kodu
docker compose down                  # stop (wolumeny zostają)
docker compose down -v               # stop + usunięcie wolumenów (baza, RAG) - nieodwracalne
```

Kopia bazy aplikacji (wolumen `chatbot-db`):

```bash
docker compose run --rm --entrypoint sh backend -c "cp /app/db/chatbot.db /app/db/chatbot.db.bak-$(date +%F)"
```

## Praca lokalna bez Dockera

Wymagania: Python 3.12, Node.js 22+ (wymagany przez Vite/Vitest; obraz Dockera używa Node 24). Wszystkie polecenia z katalogu głównego repo, chyba że napisano inaczej.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # uzupełnij jak w sekcji Docker
python -m alembic upgrade head     # tworzy/aktualizuje chatbot.db
```

W `.env` ustaw `OIDC_REDIRECT_URI=http://localhost:5173/api/auth/callback` (adres musi być zarejestrowany w kliencie Keycloaka). Przy `LLM_PROVIDER=ollama` potrzebna jest lokalna Ollama z modelem (`ollama pull qwen2.5:14b`) pod `OLLAMA_HOST` (domyślnie `http://localhost:11434`).

Backend (port 8000):

```bash
uvicorn src.backend.main:app --reload
```

Frontend (port 5173, Vite przekazuje `/api/*` do `http://127.0.0.1:8000` z obciętym `/api`; inny adres: `VITE_BACKEND_URL`):

```bash
cd src/frontend
npm ci
npm run dev
```

Otwieraj **http://localhost:5173** (nie `127.0.0.1` — ciasteczko sesji jest przypisane do hosta).

> **Tylko jeden worker uvicorna.** Blokady odświeżania tokenów, blokady rozmów i pętla czyszcząca historię działają w obrębie jednego procesu. Nie uruchamiaj backendu z `--workers` > 1.

Po zmianie `.env` zrestartuj backend (`.env` jest czytany przy starcie). Model embeddingowy pobiera się z Hugging Face przy pierwszym użyciu.

Testy i jakość kodu:

```bash
python -m pytest                   # testy backendu (tests/)
cd src/frontend && npm run lint && npm run test && npm run build
```

Migracje bazy (tworzenie, cofanie, historia): [alembic/README](alembic/README). Bazę `chatbot.db` sprzed logowania przez KSI, założoną przez `create_all()` (bez tabeli `alembic_version`), zmigruj jednorazowo:

```bash
python -m alembic stamp d509882390a9
python -m alembic upgrade head
```

## Dane: scraping i ingest

Scrapery uruchamiaj lokalnie, **z katalogu głównego repo** (zapisują do `data/<źródło>/`, ścieżki są względne):

```bash
pip install -r pipeline/requirements.txt

# strony wydziałowe -> data/strony/webiste_data.txt
python pipeline/scrapers/strony/scraper.py

# pracownicy z USOS API -> data/usos/staff/ (wymaga USOS_CONSUMER_KEY/SECRET w .env)
python pipeline/scrapers/usos/scrape_staff.py
# opcjonalnie z adresami e-mail: najpierw jednorazowe logowanie OAuth,
# które zapisuje USOS_ACCESS_TOKEN i USOS_ACCESS_TOKEN_SECRET do .env
python pipeline/scrapers/usos/usos_login.py
python pipeline/scrapers/usos/scrape_staff.py --with-email

# pliki z Mordoru -> data/mordor/ (wymaga MORDOR_COOKIE w .env)
python pipeline/scrapers/mordor/files_downloader.py
```

Ingest do indeksu RAG (`dataset/vectorstore/` i `dataset/lexical.db`):

```bash
python -m pipeline.ingest.run_ingest                            # wszystkie źródła
python -m pipeline.ingest.run_ingest --source strony --source usos
python -m pipeline.ingest.run_ingest --source usos --purge      # nadpisz zmienione rekordy
python -m pipeline.ingest.run_ingest --rebuild-lexical          # odbuduj FTS5 z vectorstore
```

- Bez `--purge` rekordy już zapisane są pomijane.
- `--source` można podać wielokrotnie (`mordor`, `strony`, `usos`).
- W Dockerze to samo: `docker compose exec backend python -m pipeline.ingest.run_ingest ...`, potem `docker compose restart backend`.

## Logowanie (OIDC, Keycloak KSI)

- Backend jest klientem poufnym (wzorzec BFF): sam wymienia kod na tokeny (Authorization Code + PKCE S256) i przechowuje je zaszyfrowane w bazie. Przeglądarka dostaje tylko ciasteczko sesji `HttpOnly`.
- Wchodzą wyłącznie osoby z grupy `OIDC_REQUIRED_GROUP` (domyślnie `/Członek`). Nie ma trybu gościa ani haseł w aplikacji.
- Członkostwo jest sprawdzane w Keycloaku (userinfo) **przy każdym** chronionym zapytaniu: usunięcie z grupy daje 403 `not_member`, wylogowanie lub blokada konta 401 `session_expired` — w obu przypadkach sesja jest kasowana od razu.
- Gdy Keycloak nie odpowiada: 503 `provider_unavailable` (dostęp jest blokowany, sesja zostaje).
- Zapytania `POST`/`DELETE` z nagłówkiem `Origin` spoza dozwolonych adresów dostają 403 `forbidden_origin`.
- Zmiana `AUTH_SECRET_KEY` wylogowuje wszystkich.
- Endpointy (przez nginx z prefiksem `/api`): `GET /auth/login`, `GET /auth/callback`, `GET /auth/me`, `POST /auth/logout`.

| Zmienna | Wymagana | Domyślnie / przykład |
|---|---|---|
| `OIDC_ISSUER` | tak | `https://auth.ksi.sh/realms/ksi` |
| `OIDC_CLIENT_ID` | tak | `chatbot` |
| `OIDC_CLIENT_SECRET` | tak | od adminów KSI, nigdy w repo |
| `OIDC_REDIRECT_URI` | tak | `https://chat.ksi.sh/api/auth/callback` |
| `AUTH_SECRET_KEY` | tak | min. 32 znaki |
| `OIDC_REQUIRED_GROUP` | nie | `/Członek` |
| `OIDC_GROUPS_CLAIM` | nie | `groups` |
| `OIDC_SCOPES` | nie | `openid profile email` |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | nie | origin `OIDC_REDIRECT_URI` + `/` |
| `OIDC_ID_TOKEN_ALGORITHMS` | nie | RS\*, PS\*, ES\*, EdDSA (HS\* i `none` zabronione) |
| `OIDC_HTTP_TIMEOUT` | nie | `10` (s) |
| `AUTH_SESSION_MAX_AGE_HOURS` | nie | `168` |
| `AUTH_FRONTEND_URL` | nie | `/` |
| `AUTH_COOKIE_SECURE` | nie | wg schematu `OIDC_REDIRECT_URI` (https → `Secure` + prefiks `__Host-`) |
| `FRONTEND_ORIGINS` | nie | `http://localhost:5173`; origin `OIDC_REDIRECT_URI` jest dopuszczony zawsze |

### Konfiguracja klienta `chatbot` w Keycloaku (realm `ksi`)

- Client authentication **ON**, Standard flow **ON**, PKCE **S256**; Direct access grants, Implicit, Service accounts **OFF**.
- Valid redirect URIs: `https://chat.ksi.sh/api/auth/callback` (lokalnie także `http://localhost:8080/api/auth/callback` i `http://localhost:5173/api/auth/callback`).
- Valid post logout redirect URIs: `https://chat.ksi.sh/` (lokalnie odpowiednio `http://localhost:8080/`, `http://localhost:5173/`).
- Mapper **Group Membership**: claim `groups`, Full group path **ON**, Add to userinfo **ON**. Bez niego każde logowanie kończy się `not_member`.

### Wdrożenie na `chat.ksi.sh`

Migracja `7c3e1f2a9b40` **kasuje wszystkie konta** starego systemu (rozmowy zostają jako anonimowe i wygasają po okresie retencji). Uprzedź użytkowników.

1. Kopia bazy:
   ```bash
   docker compose run --rm --entrypoint sh backend -c "cp /app/db/chatbot.db /app/db/chatbot.db.bak-pre-oidc"
   ```
2. W `.env` na VM ustaw zmienne logowania: `OIDC_REDIRECT_URI=https://chat.ksi.sh/api/auth/callback`, `OIDC_CLIENT_SECRET` i nowy `AUTH_SECRET_KEY` (inny niż lokalnie).
3. `git pull`, potem `docker compose up -d --build` (albo `./scripts/docker-up.sh`, z `--ollama` przy `LLM_PROVIDER=ollama`). Migracje wykonają się przy starcie backendu.
4. Sprawdź:
   ```bash
   docker compose logs backend | grep -iE "alembic|AuthConfigError|error"
   docker compose exec backend curl -s https://auth.ksi.sh/realms/ksi/.well-known/openid-configuration | head -c 120
   curl -s https://chat.ksi.sh/api/auth/me     # {"detail":{"code":"not_authenticated",...}}
   ```
5. Zaloguj się kontem z grupy `/Członek`, potem sprawdź konto spoza grupy.

Reverse proxy z TLS przed frontendem musi przekazywać ścieżki `/api/*` bez zmian.

## Historia rozmów

- Na konto przechowywanych jest **10** najnowszych rozmów — nowa rozmowa ponad limit usuwa najstarszą.
- Rozmowa bez nowej wiadomości przez **30 dni** jest usuwana (także stare rozmowy anonimowe). Backend sprawdza to przy starcie i co **6 h**.
- Konfiguracja w `.env`: `CHAT_HISTORY_MAX_PER_USER`, `CHAT_HISTORY_RETENTION_DAYS`, `CHAT_HISTORY_PURGE_INTERVAL_HOURS`.
- Do promptu trafia tylko część historii: `CHAT_HISTORY_MESSAGES` wiadomości, każda przycięta do `CHAT_HISTORY_CHAR_LIMIT` znaków.

## Zespół

**Mentor:** Oliwier Polak (@Kangurur)

- Karol Dziekan (@Dariooo23)
- Patrycja Jaworska (@zazu1023)
- Sonia Skuczeń (@SonSku)
- Mikołaj Suchan (@Wuchan33)
- Aleksandra Woźny (@olkaa566)
