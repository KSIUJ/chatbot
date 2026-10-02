# Chatbot WMiI UJ

Chatbot odpowiadający na pytania o Wydział Matematyki i Informatyki UJ — studia, pracowników, dyżury, sprawy organizacyjne. Projekt Koła Studentów Informatyki UJ (KSI), dostępny dla członków KSI pod adresem https://chat.ksi.sh.

## Jak to działa

- **Frontend** (React + Vite + Tailwind) — czat z historią rozmów, logowanie przez Keycloak KSI.
- **Backend** (FastAPI + SQLite) — dla każdego pytania szuka kontekstu (RAG: wyszukiwanie wektorowe w Chroma + pełnotekstowe SQLite FTS5 + wyszukiwanie pracowników) i przekazuje go do modelu językowego: lokalnej Ollamy (domyślnie `qwen2.5:14b`) albo API Claude / OpenRouter / Cursor (`LLM_PROVIDER`).
- Odpowiedź pojawia się na bieżąco (strumieniowo, `POST /chat/stream`), w języku interfejsu (te same języki co logowanie KSI: polski, angielski, niemiecki, hiszpański, francuski, włoski, ukraiński; domyślnie język przeglądarki), z listą źródeł: strony wydziału, profile pracowników w USOS, pliki z Mordoru.
- **Dane** pochodzą ze stron wydziału, USOS API (pracownicy) i Mordoru (materiały studenckie). Scrapery i ingest do bazy RAG są w `pipeline/`.
- Wchodzą tylko osoby z grupy `/Członek` w Keycloaku KSI; członkostwo jest sprawdzane przy każdym zapytaniu.
- Odpowiedzi można oceniać (kciuk w górę / w dół) i zgłaszać (błąd, nieaktualne, nieodpowiednie, inne); oceny z kopią pytania i odpowiedzi przegląda zarząd — grupa `OIDC_ADMIN_GROUP` (domyślnie `/Zarząd`) — przez `/api/admin/feedback` (lista, obsługa zgłoszeń, eksport CSV).
- Prompt systemowy zawiera dzisiejszą datę i rok akademicki; próby obejścia jego zasad (heurystyka backendu i znacznik od modelu) są zapisywane jako incydenty dla zarządu (`/Zarząd`) — `/api/admin/incidents`, z danymi osoby, kasowane po 180 dniach.
- Każda osoba ma dzienny limit pytań (domyślnie 10); limity, zgłoszenia, incydenty i diagnostykę obsługuje zarząd w panelu administratora (niżej).

```
src/backend/     API: auth/ (OIDC), llm/ (dostawcy modeli), rag/ (wyszukiwanie), limits/, admin/, history.py
src/frontend/    aplikacja React (+ nginx w obrazie Dockera)
pipeline/        scrapers/ (mordor, strony, usos) i ingest/ (ładowanie danych do bazy RAG)
alembic/         migracje bazy aplikacji
tests/           testy backendu (pytest)
```

## Uruchomienie (Docker)

```bash
cp .env.example .env    # uzupełnij OIDC_CLIENT_SECRET, AUTH_SECRET_KEY i klucz wybranego LLM
docker compose up -d --build                     # LLM przez API (claude/openrouter/cursor)
docker compose --profile ollama up -d --build    # z lokalną Ollamą (LLM_PROVIDER=ollama)
```

- Aplikacja: http://localhost:8080 (`FRONTEND_PORT`). Nginx przekazuje `/api/*` do backendu.
- Backend przy starcie wykonuje migracje (`alembic upgrade head`).
- GPU dla Ollamy: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d --build`.
- Backend w Dockerze łączy się z Ollamą z kontenera (`OLLAMA_HOST=http://ollama:11434` w `docker-compose.yml`).
- Po zmianie `.env`: `docker compose up -d`. Logi: `docker compose logs -f backend`.

Dane RAG (wolumeny `chatbot-data`, `chatbot-dataset`) są na starcie puste. Skopiuj lokalne dane albo zbuduj indeks w kontenerze:

```bash
docker compose cp data/. backend:/app/data
docker compose cp dataset/. backend:/app/dataset      # gotowy indeks albo:
docker compose exec backend python -m pipeline.ingest.run_ingest
docker compose restart backend
```

Kopia bazy kont i rozmów (wolumen `chatbot-db`):

```bash
docker compose exec backend cp /app/db/chatbot.db /app/db/chatbot.db.bak
```

## Praca lokalna

Python 3.12 i Node.js 22+. Polecenia z katalogu głównego repo.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m alembic upgrade head                      # tworzy/aktualizuje chatbot.db
uvicorn src.backend.main:app --reload               # API na :8000, zawsze jeden worker

cd src/frontend && npm ci && npm run dev            # http://localhost:5173
```

W `.env` ustaw `OIDC_REDIRECT_URI=http://localhost:5173/api/auth/callback` i otwieraj `localhost`, nie `127.0.0.1`.

Testy: `python -m pytest` oraz w `src/frontend`: `npm run lint && npm test && npm run build`.

Migracje: po zmianie `src/backend/models.py` wygeneruj plik `python -m alembic revision --autogenerate -m "opis"`, sprawdź go i zastosuj `python -m alembic upgrade head`.

## Dane: scraping i ingest

Scrapery zapisują do `data/<źródło>/`, ingest buduje indeks w `dataset/`:

```bash
python pipeline/scrapers/strony/scraper.py         # strony wydziału
python pipeline/scrapers/usos/scrape_staff.py      # pracownicy (USOS_CONSUMER_KEY/SECRET)
python pipeline/scrapers/mordor/files_downloader.py  # Mordor (MORDOR_COOKIE)
python -m pipeline.ingest.run_ingest               # --source usos, --purge, --rebuild-lexical
```

E-maile pracowników: najpierw jednorazowo `python pipeline/scrapers/usos/usos_login.py`, potem `scrape_staff.py --with-email`.

## Logowanie (Keycloak KSI)

Backend jest klientem poufnym OIDC (Authorization Code + PKCE): tokeny trzyma zaszyfrowane w bazie, przeglądarka dostaje tylko ciasteczko sesji `HttpOnly`. Usunięcie z grupy odbiera dostęp przy następnym zapytaniu.

Klient `chatbot` w realmie `ksi`:
- Client authentication i Standard flow włączone, PKCE S256.
- Valid redirect URIs: `https://chat.ksi.sh/api/auth/callback` (lokalnie też `http://localhost:8080/...` i `http://localhost:5173/...`).
- Valid post logout redirect URIs: `https://chat.ksi.sh/`.
- Mapper *Group Membership*: claim `groups`, Full group path i Add to userinfo włączone.

Wdrożenie na `chat.ksi.sh`: zrób kopię bazy, ustaw w `.env` na serwerze `OIDC_REDIRECT_URI=https://chat.ksi.sh/api/auth/callback`, `OIDC_CLIENT_SECRET`, nowy `AUTH_SECRET_KEY` i klucz LLM, potem `git pull && docker compose up -d --build`. Reverse proxy z TLS musi przekazywać `/api/*` bez zmian i nie buforować ani nie kompresować odpowiedzi `text/event-stream` (inaczej odpowiedzi nie będą się pojawiać na bieżąco).

Pozostałe zmienne (historia rozmów, RAG, modele) są opisane w `.env.example`.

## Panel administratora

Dostęp mają osoby z grupy `OIDC_ADMIN_GROUP` (domyślnie `/Zarząd`): w czacie *Ustawienia → Panel administratora*. Backend sprawdza grupę przy każdym zapytaniu `/api/admin/*` (bez niej 403).

- **Limity** — globalny dzienny limit pytań na osobę (domyślnie `CHAT_DAILY_LIMIT=10`) i wyjątki per osoba: własny limit, bez limitu albo 0 (zablokowana), z notatką. Admini nie są zwolnieni z limitu — mogą nadać wyjątek sobie. Doba kończy się o północy czasu polskiego. Liczy się każde pytanie, które dochodzi do modelu (także regeneracja i ponowienie); pytanie wraca do puli tylko po błędzie po stronie serwera (błąd modelu, pusta odpowiedź, nieudany zapis), a rozłączenie lub przerwanie przez użytkownika (Stop, zamknięcie karty) w dowolnym momencie liczy się jak pytanie. Po wyczerpaniu limitu `/chat` i `/chat/stream` zwracają `429` (`rate_limited`, `reset_at`, nagłówek `Retry-After`), a użytkownik widzi komunikat z godziną odnowienia; stan zwraca `GET /api/usage`. Tu są też limity załączników (rozmiar pliku, plików w wiadomości, załączników dziennie, typy plików) — zapisywane już teraz, egzekwowane przez funkcję załączników (`get_attachment_limits(db)` w `src/backend/limits/settings.py`).
- **Zgłoszenia** — zgłoszone odpowiedzi z kopią pytania, odpowiedzi i źródeł; rozwiązanie / odrzucenie z notatką, eksport CSV.
- **Incydenty** — próby obejścia promptu z danymi osoby i dopasowanymi regułami.
- **Diagnostyka** — dostawca i model, czas działania, statystyki wywołań modelu od startu (błędy, średni czas i p95, ostatni błąd), pytania i aktywni użytkownicy (dziś / 7 dni), liczba kont, rozmów i wiadomości, otwarte zgłoszenia i incydenty, rozmiar indeksu RAG i data ostatniego ingestu, rozmiar bazy i wolne miejsce na dysku.

Wartości z `.env` (`CHAT_DAILY_LIMIT`, `ATTACHMENT_*`) są domyślne — zmiana w panelu zapisuje się w bazie (tabela `app_settings`) i ma pierwszeństwo. Dzienne liczniki starsze niż 90 dni są kasowane w tle.

## Autorzy

Mentor: Oliwier Polak ([@Kangurur](https://github.com/Kangurur))

- Karol Dziekan ([@Dariooo23](https://github.com/Dariooo23))
- Patrycja Jaworska ([@zazu1023](https://github.com/zazu1023))
- Sonia Skuczeń ([@SonSku](https://github.com/SonSku))
- Mikołaj Suchan ([@Wuchan33](https://github.com/Wuchan33))
- Aleksandra Woźny ([@olkaa566](https://github.com/olkaa566))
