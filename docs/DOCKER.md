# Dockeryzacja — jak postawić cały stos

Backend (FastAPI + RAG) i frontend (React, serwowany przez nginx) w
kontenerach, z opcjonalnym lokalnym LLM (Ollama). Ten dokument opisuje
wyłącznie uruchomienie przez Docker. Dla pracy bez Dockera (venv, `npm run
dev`, scraping, ingest RAG) patrz [SETUP.md](SETUP.md).

Stan zweryfikowany: `docker compose build` + `docker compose up -d`
przetestowane end-to-end na tej maszynie (Windows 11 + Docker Desktop) —
build obu obrazów, healthchecki, proxy nginksa `/api/*` → backend, i realny
retrieval RAG po załadowaniu danych do wolumenów.

---

## 1. Wymagania

- Docker Desktop (Windows/macOS) lub Docker Engine + Compose v2 (Linux).
- Konto/klucz do wybranego dostawcy LLM (Cursor, Claude/Anthropic lub
  OpenRouter) — **albo** chęć pobrania lokalnego modelu przez Ollamę
  (kilka–kilkanaście GB, wolniej bez GPU).
- Opcjonalnie: karta NVIDIA + [NVIDIA Container
  Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html),
  jeśli chcesz przyspieszyć Ollamę / encoder RAG. Bez tego wszystko działa na
  CPU (wolniej, ale działa — tak było testowane).

---

## 2. Szybki start

```bash
./scripts/docker-up.sh
```

Skrypt: tworzy `.env` z `.env.example` (jeśli nie istnieje), buduje obrazy i
odpala `backend` + `frontend`. Otwórz **http://localhost:8080**.

Flagi:

```bash
./scripts/docker-up.sh --ollama          # + lokalny model przez Ollame
./scripts/docker-up.sh --ollama --gpu    # + akceleracja NVIDIA
```

Bez skryptu, ręcznie to samo to:

```bash
cp .env.example .env   # jesli .env jeszcze nie istnieje
docker compose up -d --build                                    # bez Ollamy
docker compose --profile ollama up -d --build                   # z Ollama
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d --build   # z Ollama + GPU
```

**Uwaga:** świeży `docker compose up` startuje z **pustą bazą RAG** — patrz
sekcja 5. Chatbot odpowie, ale nie będzie znał realiów wydziału, dopóki nie
załadujesz danych.

---

## 3. Wybór dostawcy LLM

Ustawiane w `.env` (przekazywane do kontenera `backend` przez `env_file`).
Domyślnie `LLM_PROVIDER=ollama`. Pełny opis wszystkich zmiennych jest w
komentarzach `.env.example` — tu tylko skrót:

| `LLM_PROVIDER` | Wymaga w `.env` | Uwagi |
|---|---|---|
| `ollama` (domyślne) | — | wymaga `--ollama` przy starcie (sekcja 2); pierwsze uruchomienie ściąga model (`OLLAMA_MODEL`, domyślnie `qwen2.5:14b`) |
| `claude` | `ANTHROPIC_API_KEY` | najszybszy/najstabilniejszy do demo |
| `cursor` | `CURSOR_API_KEY` | Cursor Cloud Agents — **60–90 s na odpowiedź**, provisioning VM per zapytanie |
| `openrouter` | `OPENROUTER_API_KEY` | jedno API do wielu dostawców |

Po zmianie `.env` zawsze **zrestartuj backend**:
`docker compose restart backend` (patrz sekcja 7 — `load_dotenv()` czyta
plik raz, przy starcie procesu).

---

## 4. GPU (opcjonalnie)

`docker-compose.gpu.yml` to nakładka, nie osobny stos — dokłada rezerwację
NVIDIA do `ollama` i `backend` (`RAG_DEVICE=cuda` dla encodera). Celowo NIE
jest częścią domyślnego `docker-compose.yml`: na maszynie bez karty
NVIDIA/Container Toolkit `docker compose up` z twardą rezerwacją GPU **w
ogóle nie startuje** (`could not select device driver "nvidia"`). Dodajesz
ją świadomie flagą `--gpu` / `-f docker-compose.gpu.yml`.

---

## 5. Dane RAG (najważniejsza sekcja)

Wolumeny `chatbot-data` i `chatbot-dataset` (surowe scrapy + baza wektorowa
Chroma + indeks FTS5) są puste przy pierwszym `docker compose up` — obraz
backendu ich celowo nie zawiera (`.dockerignore`), to dane, nie kod.

### Wariant A — masz już dane lokalnie (z pracy bez Dockera, [SETUP.md](SETUP.md))

```bash
./scripts/docker-seed-data.sh
```

Kopiuje lokalne `data/` i `dataset/` do wolumenów Dockera (przez jednorazowy
kontener na obrazie `backend`, bez zależności typu Ollama) i restartuje
backend. Bezpieczne do wielokrotnego odpalenia (nadpisuje tym samym).

### Wariant B — nie masz jeszcze nic zescrapowanego

Scraper i ingest **nie są częścią obrazu backendu** (`Dockerfile` kopiuje
tylko `src/backend`, nie `src/data`) — to świadome uproszczenie, scraping to
jednorazowa, lokalna czynność. Zrób to na hoście (poza Dockerem) wg
[SETUP.md](SETUP.md#6-dane-i-baza-wektorowa) rozdziały 6–7, a potem uruchom
`./scripts/docker-seed-data.sh` z Wariantu A.

### Weryfikacja

```bash
docker compose exec backend python -c "from src.backend.RAG.vectorstore import VectorStore; c=VectorStore().collection; print({s: len(c.get(where={'source': s})['ids']) for s in ['mordor','strony','usos']}, 'total', c.count())"
```

Stan referencyjny (dane z tej maszyny, bez Mordoru): `strony: 991, usos: 208,
mordor: 0, total: 1199`.

---

## 6. Porty i architektura

```
przeglądarka --80--> [frontend: nginx]  --statyczne pliki React--
                            |
                            +--/api/*--> [backend: FastAPI]:8000 --> SQLite (chatbot-db)
                                              |                  --> Chroma + FTS5 (chatbot-dataset)
                                              |                  --> scrapy (chatbot-data)
                                              +--(jesli LLM_PROVIDER=ollama)--> [ollama]:11434
```

- **Frontend**: `http://localhost:${FRONTEND_PORT:-8080}` — jedyny adres,
  który realnie klikasz. Frontend woła zawsze własny origin pod `/api/*`;
  nginx (`src/frontend/nginx.conf`) przepisuje to na `backend:8000/*` w
  wewnętrznej sieci Compose. Zero CORS, zero zaszytego adresu backendu w
  buildzie frontendu.
- **Backend bezpośrednio**: `http://localhost:8000` też jest opublikowany na
  hosta (przydatne do debugowania: `curl http://localhost:8000/health`), ale
  frontend go nie używa bezpośrednio.

---

## 7. Zarządzanie stosem

```bash
docker compose logs -f backend        # logi na żywo
docker compose ps                     # status + healthcheck
docker compose restart backend        # po zmianie .env albo danych RAG
docker compose up -d --build          # po zmianie kodu (przebudowuje obrazy)
docker compose down                   # stop + usuniecie kontenerow (wolumeny ZOSTAJA)
docker compose down -v                # jw. + kasuje TEZ wolumeny (baza, RAG, historia czatu - nieodwracalne)
```

---

## 8. Troubleshooting

Realne problemy napotkane i naprawione podczas stawiania tego stosu — jeśli
edytujesz pliki Dockera, łatwo je odtworzyć:

| Objaw | Przyczyna | Fix |
|---|---|---|
| `exec /entrypoint.sh: no such file or directory` w logach backendu | Windows (`core.autocrlf=true`) zamienia `LF` na `CRLF` przy checkout — shebang `#!/bin/sh\r` nie istnieje jako interpreter w kontenerze Linux. | Wymuszone przez [.gitattributes](../.gitattributes) (`*.sh text eol=lf`). Jeśli mimo to wróci: sprawdź `file docker/entrypoint.sh` (musi być bez `CRLF`), popraw i zacommituj ponownie. |
| `/api/...` przez nginx zwraca **404**, mimo że backend działa (`curl localhost:8000/...` OK) | `proxy_pass` ze zmienną (`$backend_upstream`, potrzebne do leniwego DNS Dockera) **nie** obcina automatycznie prefiksu `location` tak jak `proxy_pass` z literalnym adresem — `/api/health` leci do backendu jako `/api/health`, a nie `/health`. | Jawny `rewrite ^/api/(.*)$ /$1 break;` w [nginx.conf](../src/frontend/nginx.conf) przed `proxy_pass`. |
| `/api/...` przez nginx zwraca **500** + w logu `using uninitialized "backend_upstream" variable` | `rewrite ... break` kończy fazę rewrite w nginxie — `set` napisany PO nim się nie wykonuje. | Kolejność w `nginx.conf`: najpierw `set $backend_upstream ...;`, potem `rewrite ... break;`. |
| `docker compose up` odmawia startu: `could not select device driver "nvidia"` | Rezerwacja GPU w compose, brak karty/Container Toolkit. | Nie używaj `--gpu` / `docker-compose.gpu.yml` bez NVIDIA Container Toolkit. Domyślny `docker-compose.yml` działa czysto na CPU. |
| Backend nie widzi nowego `LLM_PROVIDER`/klucza z `.env` | `load_dotenv()` (`src/backend/config.py`, `database.py`) czyta `.env` raz, przy imporcie/starcie procesu. | `docker compose restart backend` po każdej zmianie `.env`. |
| Chatbot odpowiada, ale "nic nie wie" o wydziale | Świeże wolumeny `chatbot-data`/`chatbot-dataset` są puste. | Sekcja 5 — `./scripts/docker-seed-data.sh`. |
| `docker compose run ... backend sh -c "..."` uruchamia PEŁNY serwer zamiast Twojej komendy | `ENTRYPOINT` (`/entrypoint.sh`) w obrazie backendu ignoruje przekazane argumenty (zawsze robi `alembic upgrade head` + `exec uvicorn`) - `run backend <cmd>` podmienia tylko CMD, nie ENTRYPOINT. | Dodaj `--entrypoint sh` do `docker compose run` (tak robi [docker-seed-data.sh](../scripts/docker-seed-data.sh)). |
| Skrypty w `scripts/*.sh` gubią ścieżki / bind mounty nie działają (Windows, Git Bash) | Git Bash przepisuje argumenty wyglądające jak ścieżki POSIX na ścieżki Windowsa. | Oba skrypty ustawiają `MSYS_NO_PATHCONV=1` same z siebie - nie trzeba nic dodatkowo robić, bez znaczenia na Linux/macOS. |

---

## 9. Struktura plików

```
Dockerfile                    backend (Python 3.12-slim + torch/chromadb itd.)
.dockerignore                 co NIE trafia do obrazu backendu (data/, dataset/, .env, testy...)
docker/entrypoint.sh           alembic upgrade head -> uvicorn
docker-compose.yml             backend + frontend (domyslne, CPU) + ollama/ollama-pull (profil "ollama")
docker-compose.gpu.yml         nakladka: GPU dla ollama + backend (uzyj z -f, patrz sekcja 4)
src/frontend/Dockerfile        multi-stage: node (vite build) -> nginx (statyka + proxy /api/)
src/frontend/nginx.conf        proxy /api/* -> backend:8000/* (patrz sekcja 8 - kolejnosc set/rewrite)
scripts/docker-up.sh           budowa + start (z .env, profilami --ollama/--gpu)
scripts/docker-seed-data.sh    kopiuje lokalne data/+dataset/ do wolumenow
.gitattributes                 wymusza LF dla *.sh i Dockerfile (patrz sekcja 8)
```
