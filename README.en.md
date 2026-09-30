<h1 align="center">JU Faculty of Mathematics and Computer Science Chatbot</h1>

<p align="center">
  A RAG chatbot answering student and prospective-student questions about the Faculty of Mathematics and Computer Science at Jagiellonian University.
  <br>A project of the KSI student club (Koło Studentów Informatyki).
</p>

<p align="center"><a href="README.md">Polski</a> · <b>English</b></p>

---

## Table of contents

- [How it works](#how-it-works)
- [Repository layout](#repository-layout)
- [Running with Docker](#running-with-docker)
- [Local development without Docker](#local-development-without-docker)
- [Data: scraping and ingest](#data-scraping-and-ingest)
- [Login (OIDC, KSI Keycloak)](#login-oidc-ksi-keycloak)
- [Chat history](#chat-history)
- [Team](#team)

## How it works

- The **frontend** (React) sends a question to the **backend** (FastAPI).
- The backend retrieves context with **hybrid search**: vector search (Chroma, `sdadas/mmlw-roberta-large` embeddings) + an SQLite FTS5 lexical index + staff lookup by name (USOS data).
- Data sources: faculty websites (`strony`), staff from the USOS API (`usos`), student materials from Mordor (`mordor`).
- The answer comes from the LLM selected with `LLM_PROVIDER`: `ollama` (default, local model `qwen2.5:14b`), `claude`, `openrouter` or `cursor`.
- Only KSI members have access (login through KSI Keycloak). Accounts, sessions and conversations live in the SQLite database `chatbot.db`.

## Repository layout

```
src/backend/          FastAPI: main.py (/chat, /conversations, /auth/*, /api/stats, /health)
  auth/               OIDC login through KSI Keycloak
  history.py          chat history limits and retention
  llm/                LLM providers (ollama, claude, openrouter, cursor), http_api.py - shared helper
  rag/                retrieval: encoder, vectorstore (Chroma), lexical (FTS5), staff, context_builder, schema
src/frontend/         React 19 + Vite + Tailwind 4 + TypeScript, nginx.conf for the Docker image
pipeline/
  scrapers/           mordor, strony, usos - fetch data into data/<source>/
  ingest/             loads data/ into the RAG index in dataset/
alembic/              application database migrations (SQLite chatbot.db)
tests/backend/        pytest tests
scripts/              docker-up.sh, docker-seed-data.sh
data/                 raw scraped data (not in git)
dataset/              RAG index: vectorstore/ (Chroma) and lexical.db (FTS5) (not in git)
```

## Running with Docker

Requirements: Docker with Compose v2 (`docker compose`). An NVIDIA GPU is optional. On Windows run `scripts/*.sh` in Git Bash.

### 1. Configuration

```bash
cp .env.example .env
```

In `.env` fill in at least:

- `OIDC_CLIENT_SECRET` (from the KSI admins) and `AUTH_SECRET_KEY` (at least 32 characters):
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- `OIDC_REDIRECT_URI` — defaults to `http://localhost:8080/api/auth/callback` (port = `FRONTEND_PORT`).
- The API key of the chosen provider if `LLM_PROVIDER` is not `ollama`: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` or `CURSOR_API_KEY`.

Without the required login variables the backend will not start (the logs show an `AuthConfigError` listing everything that is missing). All other variables are described in `.env.example`.

### 2. Start

```bash
./scripts/docker-up.sh                 # backend + frontend (LLM via API)
./scripts/docker-up.sh --ollama        # + local Ollama (needed with LLM_PROVIDER=ollama)
./scripts/docker-up.sh --ollama --gpu  # + NVIDIA GPU (requires NVIDIA Container Toolkit)
```

The script creates `.env` from `.env.example` if it is missing and runs `docker compose ... up -d --build`. Manual equivalents:

```bash
docker compose up -d --build
docker compose --profile ollama up -d --build
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d --build
```

- Ollama is in the `ollama` profile and does not start without it. On the first run `ollama-pull` downloads `OLLAMA_MODEL` (default `qwen2.5:14b`, several GB) into the `ollama-data` volume.
- `docker-compose.gpu.yml` adds a GPU reservation for `ollama` and `backend` (`RAG_DEVICE=cuda`). Without an NVIDIA card the stack will not start with this file.
- Frontend: **http://localhost:8080** (`FRONTEND_PORT`). Backend directly: http://localhost:8000/health. Both ports are published on `127.0.0.1` only.
- nginx in the frontend image proxies `/api/*` to the backend and strips the `/api` prefix (e.g. `/api/auth/me` → `/auth/me`).
- On start the backend runs `alembic upgrade head` and then uvicorn (`docker/entrypoint.sh`).

### 3. RAG data

Fresh `chatbot-data` and `chatbot-dataset` volumes are empty — the chatbot answers but knows nothing about the faculty. To load data:

```bash
# copies local data/ and dataset/ into the volumes and restarts the backend
./scripts/docker-seed-data.sh

# if you only copied raw data/ - build the index inside the container
docker compose exec backend python -m pipeline.ingest.run_ingest
docker compose restart backend
```

Scrapers are not part of the image — run them locally (see [Data](#data-scraping-and-ingest)).

### 4. Useful commands

```bash
docker compose ps                    # status and healthchecks
docker compose logs -f backend       # backend logs
docker compose exec backend sh       # shell inside the container
docker compose up -d                 # after changing .env (recreates changed containers)
docker compose up -d --build         # after changing code
docker compose down                  # stop (volumes are kept)
docker compose down -v               # stop + delete volumes (database, RAG) - irreversible
```

Backing up the application database (`chatbot-db` volume):

```bash
docker compose run --rm --entrypoint sh backend -c "cp /app/db/chatbot.db /app/db/chatbot.db.bak-$(date +%F)"
```

## Local development without Docker

Requirements: Python 3.12, Node.js 22+ (required by Vite/Vitest; the Docker image uses Node 24). Run all commands from the repository root unless stated otherwise.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # fill in as in the Docker section
python -m alembic upgrade head     # creates/updates chatbot.db
```

In `.env` set `OIDC_REDIRECT_URI=http://localhost:5173/api/auth/callback` (the URI must be registered in the Keycloak client). With `LLM_PROVIDER=ollama` you need a local Ollama with the model (`ollama pull qwen2.5:14b`) at `OLLAMA_HOST` (default `http://localhost:11434`).

Backend (port 8000):

```bash
uvicorn src.backend.main:app --reload
```

Frontend (port 5173; Vite proxies `/api/*` to `http://127.0.0.1:8000` with `/api` stripped; override with `VITE_BACKEND_URL`):

```bash
cd src/frontend
npm ci
npm run dev
```

Open **http://localhost:5173** (not `127.0.0.1` — the session cookie is bound to the host).

> **Single uvicorn worker only.** The token-refresh locks, conversation locks and the history cleanup loop are all in-process. Do not run the backend with `--workers` > 1.

Restart the backend after changing `.env` (it is read at startup). The embedding model is downloaded from Hugging Face on first use.

Tests and code quality:

```bash
python -m pytest                   # backend tests (tests/)
cd src/frontend && npm run lint && npm run test && npm run build
```

Database migrations (creating, reverting, history): [alembic/README](alembic/README) (in Polish). A `chatbot.db` from before KSI login that was created by `create_all()` (no `alembic_version` table) needs a one-time migration:

```bash
python -m alembic stamp d509882390a9
python -m alembic upgrade head
```

## Data: scraping and ingest

Run the scrapers locally, **from the repository root** (they write to `data/<source>/`; paths are relative):

```bash
pip install -r pipeline/requirements.txt

# faculty websites -> data/strony/webiste_data.txt
python pipeline/scrapers/strony/scraper.py

# staff from the USOS API -> data/usos/staff/ (needs USOS_CONSUMER_KEY/SECRET in .env)
python pipeline/scrapers/usos/scrape_staff.py
# optionally with e-mail addresses: first a one-time OAuth login,
# which writes USOS_ACCESS_TOKEN and USOS_ACCESS_TOKEN_SECRET to .env
python pipeline/scrapers/usos/usos_login.py
python pipeline/scrapers/usos/scrape_staff.py --with-email

# files from Mordor -> data/mordor/ (needs MORDOR_COOKIE in .env)
python pipeline/scrapers/mordor/files_downloader.py
```

Ingest into the RAG index (`dataset/vectorstore/` and `dataset/lexical.db`):

```bash
python -m pipeline.ingest.run_ingest                            # all sources
python -m pipeline.ingest.run_ingest --source strony --source usos
python -m pipeline.ingest.run_ingest --source usos --purge      # overwrite changed records
python -m pipeline.ingest.run_ingest --rebuild-lexical          # rebuild FTS5 from the vectorstore
```

- Without `--purge` already stored records are skipped.
- `--source` can be repeated (`mordor`, `strony`, `usos`).
- In Docker the same: `docker compose exec backend python -m pipeline.ingest.run_ingest ...`, then `docker compose restart backend`.

## Login (OIDC, KSI Keycloak)

- The backend is a confidential client (BFF pattern): it exchanges the code for tokens itself (Authorization Code + PKCE S256) and stores them encrypted in the database. The browser only gets an `HttpOnly` session cookie.
- Only members of the `OIDC_REQUIRED_GROUP` group (default `/Członek`) get in. There is no guest mode and no passwords in the app.
- Membership is checked in Keycloak (userinfo) on **every** protected request: removal from the group gives 403 `not_member`, logout or a blocked account gives 401 `session_expired` — in both cases the session is deleted immediately.
- When Keycloak does not respond: 503 `provider_unavailable` (access is denied, the session is kept).
- `POST`/`DELETE` requests with an `Origin` header outside the allowed origins get 403 `forbidden_origin`.
- Changing `AUTH_SECRET_KEY` logs everyone out.
- Endpoints (behind nginx with the `/api` prefix): `GET /auth/login`, `GET /auth/callback`, `GET /auth/me`, `POST /auth/logout`.

| Variable | Required | Default / example |
|---|---|---|
| `OIDC_ISSUER` | yes | `https://auth.ksi.sh/realms/ksi` |
| `OIDC_CLIENT_ID` | yes | `chatbot` |
| `OIDC_CLIENT_SECRET` | yes | from the KSI admins, never in the repo |
| `OIDC_REDIRECT_URI` | yes | `https://chat.ksi.sh/api/auth/callback` |
| `AUTH_SECRET_KEY` | yes | at least 32 characters |
| `OIDC_REQUIRED_GROUP` | no | `/Członek` |
| `OIDC_GROUPS_CLAIM` | no | `groups` |
| `OIDC_SCOPES` | no | `openid profile email` |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | no | origin of `OIDC_REDIRECT_URI` + `/` |
| `OIDC_ID_TOKEN_ALGORITHMS` | no | RS\*, PS\*, ES\*, EdDSA (HS\* and `none` are forbidden) |
| `OIDC_HTTP_TIMEOUT` | no | `10` (s) |
| `AUTH_SESSION_MAX_AGE_HOURS` | no | `168` |
| `AUTH_FRONTEND_URL` | no | `/` |
| `AUTH_COOKIE_SECURE` | no | from the scheme of `OIDC_REDIRECT_URI` (https → `Secure` + `__Host-` prefix) |
| `FRONTEND_ORIGINS` | no | `http://localhost:5173`; the origin of `OIDC_REDIRECT_URI` is always allowed |

### Keycloak client `chatbot` (realm `ksi`)

- Client authentication **ON**, Standard flow **ON**, PKCE **S256**; Direct access grants, Implicit, Service accounts **OFF**.
- Valid redirect URIs: `https://chat.ksi.sh/api/auth/callback` (for local work also `http://localhost:8080/api/auth/callback` and `http://localhost:5173/api/auth/callback`).
- Valid post logout redirect URIs: `https://chat.ksi.sh/` (locally `http://localhost:8080/`, `http://localhost:5173/`).
- **Group Membership** mapper: claim `groups`, Full group path **ON**, Add to userinfo **ON**. Without it every login ends with `not_member`.

### Deploying to `chat.ksi.sh`

Migration `7c3e1f2a9b40` **deletes all accounts** of the old system (conversations are kept as anonymous and expire after the retention period). Warn the users.

1. Back up the database:
   ```bash
   docker compose run --rm --entrypoint sh backend -c "cp /app/db/chatbot.db /app/db/chatbot.db.bak-pre-oidc"
   ```
2. In `.env` on the VM set the login variables: `OIDC_REDIRECT_URI=https://chat.ksi.sh/api/auth/callback`, `OIDC_CLIENT_SECRET` and a new `AUTH_SECRET_KEY` (different from the local one).
3. `git pull`, then `docker compose up -d --build` (or `./scripts/docker-up.sh`, with `--ollama` when `LLM_PROVIDER=ollama`). Migrations run when the backend starts.
4. Check:
   ```bash
   docker compose logs backend | grep -iE "alembic|AuthConfigError|error"
   docker compose exec backend curl -s https://auth.ksi.sh/realms/ksi/.well-known/openid-configuration | head -c 120
   curl -s https://chat.ksi.sh/api/auth/me     # {"detail":{"code":"not_authenticated",...}}
   ```
5. Log in with an account from `/Członek`, then try an account outside the group.

The TLS reverse proxy in front of the frontend must pass `/api/*` paths through unchanged.

## Chat history

- Each account keeps its **10** newest conversations — a new conversation over the limit deletes the oldest one.
- A conversation with no new message for **30 days** is deleted (including old anonymous ones). The backend checks this on startup and every **6 h**.
- Configurable in `.env`: `CHAT_HISTORY_MAX_PER_USER`, `CHAT_HISTORY_RETENTION_DAYS`, `CHAT_HISTORY_PURGE_INTERVAL_HOURS`.
- Only part of the history goes into the prompt: `CHAT_HISTORY_MESSAGES` messages, each trimmed to `CHAT_HISTORY_CHAR_LIMIT` characters.

## Team

**Mentor:** Oliwier Polak (@Kangurur)

- Karol Dziekan (@Dariooo23)
- Patrycja Jaworska (@zazu1023)
- Sonia Skuczeń (@SonSku)
- Mikołaj Suchan (@Wuchan33)
- Aleksandra Woźny (@olkaa566)
