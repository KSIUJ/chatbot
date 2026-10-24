# Chatbot WMiI UJ

Chatbot odpowiadający na pytania o Wydział Matematyki i Informatyki UJ — studia, pracowników, dyżury, sprawy organizacyjne. Projekt Koła Studentów Informatyki UJ (KSI), dostępny dla członków KSI pod adresem https://chat.ksi.sh.

## Jak to działa

- **Frontend** (React + Vite + Tailwind) — czat z historią rozmów, logowanie przez Keycloak KSI.
- **Backend** (FastAPI + SQLite) — dla każdego pytania szuka kontekstu (RAG: wyszukiwanie wektorowe w Chroma + pełnotekstowe SQLite FTS5 + wyszukiwanie pracowników) i przekazuje go do modelu językowego: lokalnej Ollamy (domyślnie `qwen2.5:14b`) albo API Claude (domyślnie Claude Haiku 5.5, `CLAUDE_MODEL`, `CLAUDE_EFFORT`) / OpenRouter / Cursor (`LLM_PROVIDER`).
- Odpowiedź pojawia się na bieżąco (strumieniowo, `POST /chat/stream`), w języku interfejsu (te same języki co logowanie KSI: polski, angielski, niemiecki, hiszpański, francuski, włoski, ukraiński; domyślnie język przeglądarki), z listą źródeł: strony wydziału, profile pracowników w USOS, pliki z Mordoru.
- **Dane** pochodzą ze stron wydziału, USOS API (pracownicy) i Mordoru (materiały studenckie). Scrapery i ingest do bazy RAG są w `pipeline/`.
- Wchodzą tylko osoby z grupy `/Członek` w Keycloaku KSI; członkostwo jest sprawdzane przy każdym zapytaniu.
- Odpowiedzi można oceniać (kciuk w górę / w dół) i zgłaszać (błąd, nieaktualne, nieodpowiednie, inne); oceny z kopią pytania i odpowiedzi przegląda zarząd — grupa `OIDC_ADMIN_GROUP` (domyślnie `/Zespoły/Zarząd`) — przez `/api/admin/feedback` (lista, obsługa zgłoszeń, eksport CSV). Kopie są anonimizowane, gdy rozmowa znika; usunięcie rozmowy przez użytkownika kasuje też jego same oceny (zostają tylko zgłoszenia), a wszystko bez zmian od roku znika w tle.
- Prompt systemowy zawiera dzisiejszą datę i rok akademicki; próby obejścia jego zasad (heurystyka backendu i znacznik od modelu) są zapisywane jako incydenty dla zarządu (`/Zespoły/Zarząd`) — `/api/admin/incidents`, z danymi osoby, kasowane po 90 dniach.
- Ostrzeżenie to incydent ze znacznikiem od modelu (osoba widzi wtedy informację o zgłoszeniu; sama heurystyka i incydenty odrzucone przez zarząd się nie liczą). Po 3 ostrzeżeniach osoba jest blokowana: `/chat`, `/chat/stream` i `/attachments` zwracają `403` (`chat_blocked`), a nad polem pytania pojawia się prośba o kontakt z członkiem zarządu KSI; historia rozmów zostaje dostępna. Blokadę zdejmuje zarząd w zakładce *Blokady*.
- Każda osoba ma dzienny limit pytań (domyślnie 10); limity, zgłoszenia, incydenty i diagnostykę obsługuje zarząd w panelu administratora (niżej).
- Do pytania można dołączyć pliki (PDF, DOCX, TXT, obrazy) — szczegóły w sekcji *Załączniki*.

```
src/backend/     API: auth/ (OIDC), llm/ (dostawcy modeli), rag/ (wyszukiwanie: sources/ — źródła danych, core/ — indeksy i retrieval, registry.py), limits/, admin/, attachments/, history.py
src/frontend/    aplikacja React (+ nginx w obrazie Dockera)
pipeline/        scrapers/ (mordor, strony, usos) i ingest/ (ładowanie danych źródeł z rejestru RAG do bazy)
alembic/         migracje bazy aplikacji
tests/           testy backendu (pytest)
```

## Uruchomienie (Docker)

Całość jednym poleceniem (Linux, macOS, Git Bash na Windows):

```bash
cp .env.example .env    # uzupełnij OIDC_CLIENT_SECRET, AUTH_SECRET_KEY i klucz wybranego LLM
./deploy.sh             # start albo aktualizacja po zmianach w kodzie
./deploy.sh --pull      # wdrożenie na serwerze: najpierw git pull
./deploy.sh --help      # pozostałe opcje (--seed, --gpu, --no-backup, --timeout)
```

`deploy.sh` sprawdza Dockera i wymagane zmienne w `.env` (nie wypisuje ich wartości), robi spójną kopię bazy kont i rozmów do `backups/` (ostatnie 10, nie starsze niż 30 dni, tylko dla właściciela pliku), buduje obrazy, startuje kontenery i czeka, aż strona odpowie pod `http://127.0.0.1:FRONTEND_PORT`. Przy `LLM_PROVIDER=ollama` sam włącza profil z Ollamą; `--seed` kopiuje lokalne `data/` i `dataset/` do kontenera. Gdy coś nie wstanie, pokazuje stan kontenerów i logi backendu. Zatrzymanie: `docker compose down`.

To samo ręcznie:

```bash
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
docker compose exec -u app backend python -m src.backend.rag.index build
```

Backend sam przechodzi na nowo zbudowany indeks (sprawdza `dataset/CURRENT` co 10 s); po skopiowaniu indeksu starego typu (bez `CURRENT`) zrestartuj backend: `docker compose restart backend`. Opis indeksu i powrotu do poprzedniego: [Dane: scraping i indeks](#dane-scraping-i-indeks).

Załączniki z czatu leżą w wolumenie `chatbot-uploads` (`/app/uploads`, `ATTACHMENTS_DIR`); znikają razem z rozmowami, więc nie trzeba ich kopiować razem z bazą.

Backend działa jako użytkownik `app` (uid 10001), bez uprawnień roota. Polecenia w kontenerze uruchamiaj z `-u app`; pliki zapisane jako root (np. przez `docker compose cp`) dostają właściciela `app` przy następnym starcie kontenera.

Kopia bazy kont i rozmów (wolumen `chatbot-db`):

```bash
docker compose exec -u app backend cp /app/db/chatbot.db /app/db/chatbot.db.bak
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

## Dane: scraping i indeks

Scrapery zapisują do `data/<źródło>/`, CLI indeksu buduje z tych zbiorów indeks RAG w `dataset/`:

```bash
python pipeline/scrapers/strony/scraper.py         # strony wydziału
python pipeline/scrapers/usos/scrape_staff.py      # pracownicy (USOS_CONSUMER_KEY/SECRET)
python pipeline/scrapers/mordor/files_downloader.py  # Mordor (MORDOR_COOKIE)
python -m src.backend.rag.index sync               # nowe, zmienione i usunięte dokumenty
```

E-maile pracowników: najpierw jednorazowo `python pipeline/scrapers/usos/usos_login.py`, potem `scrape_staff.py --with-email`.

Każdy indeks (wektory Chromy, BM25 w SQLite FTS5, `meta.json`) leży we własnym katalogu `dataset/indexes/<czas UTC>/`, a plik `dataset/CURRENT` wskazuje bieżący. Polecenia nigdy nie zmieniają indeksu, z którego korzysta backend — pracują na nowym katalogu i na końcu atomowo przełączają `CURRENT`; backend zauważa zmianę w ciągu 10 s, bez restartu. W kontenerze: `docker compose exec -u app backend python -m src.backend.rag.index …`.

| polecenie | co robi |
|---|---|
| `build` | nowy indeks od zera (wszystkie dokumenty embedowane na nowo); po zmianie modelu embeddingów, prefiksów albo podziału na chunki |
| `build --source usos` | od zera tylko wybrane źródło, pozostałe skopiowane z bieżącego indeksu (dawne `--purge`) |
| `sync [--source …]` | kopia bieżącego indeksu + tylko nowe i zmienione dokumenty (po `content_hash`), usunięcie tych, których nie ma już w danych; bez zmian nic nie przełącza |
| `status` | bieżący indeks, data, model i ustawienia z `meta.json`, liczby dokumentów w obu indeksach na źródło, ostrzeżenia o niezgodnościach |
| `rollback` | powrót do poprzedniego indeksu |
| `use <nazwa>` | przełączenie na wskazany katalog z `dataset/indexes/` |

- `meta.json` zapisuje wersję formatu, datę, model embeddingów i prefiksy, parametry chunkingu, liczby dokumentów i datę zebrania danych z `manifest.json` każdego źródła. Backend przy otwarciu indeksu porównuje je z konfiguracją (`RAG_EMBEDDING_MODEL`, `RAG_*_PREFIX`) i przy różnicy loguje ostrzeżenie; `sync` w takim indeksie odmawia (trzeba `build`). Stan widać też w panelu administratora (Diagnostyka).
- Przerwany `build`/`sync` (np. restart maszyny) wystarczy uruchomić ponownie tym samym poleceniem: zapisane partie zostają, embedowane jest tylko to, czego brakuje. Do tego czasu backend korzysta z poprzedniego indeksu.
- Zostają 2 poprzednie indeksy (do `rollback`), starsze są usuwane. Ręczny powrót: zapisz w `dataset/CURRENT` np. `indexes/20261011T120000Z`. Usunięcie `CURRENT` wraca do starego układu (`dataset/vectorstore` + `dataset/lexical.db`), który można skasować po pierwszym udanym `build`.
- Wyszukiwanie wektorowe jest dokładne (odległość do każdego wektora wybranych źródeł), więc wynik zależy tylko od zawartości indeksu.
- Stare polecenie `python -m pipeline.ingest.run_ingest` nadal działa i przekierowuje na `sync` (z `--purge` na `build`).

## Logowanie (Keycloak KSI)

Backend jest klientem poufnym OIDC (Authorization Code + PKCE): tokeny trzyma zaszyfrowane w bazie, przeglądarka dostaje tylko ciasteczko sesji `HttpOnly`. Usunięcie z grupy odbiera dostęp przy następnym zapytaniu.

Klient `chatbot` w realmie `ksi`:
- Client authentication i Standard flow włączone, PKCE S256.
- Valid redirect URIs: `https://chat.ksi.sh/api/auth/callback` (lokalnie też `http://localhost:8080/...` i `http://localhost:5173/...`).
- Valid post logout redirect URIs: `https://chat.ksi.sh/`.
- Mapper *Group Membership*: claim `groups`, Full group path i Add to userinfo włączone.

Wdrożenie na `chat.ksi.sh`: ustaw w `.env` na serwerze `OIDC_REDIRECT_URI=https://chat.ksi.sh/api/auth/callback`, `OIDC_CLIENT_SECRET`, nowy `AUTH_SECRET_KEY` i klucz LLM, potem `./deploy.sh --pull` (kopia bazy, `git pull`, przebudowa i start). Reverse proxy z TLS musi przekazywać `/api/*` bez zmian i nie buforować ani nie kompresować odpowiedzi `text/event-stream` (inaczej odpowiedzi nie będą się pojawiać na bieżąco).

Pozostałe zmienne (historia rozmów, RAG, modele) są opisane w `.env.example`.

## Panel administratora

Dostęp mają osoby z grupy `OIDC_ADMIN_GROUP` (domyślnie `/Zespoły/Zarząd`): w czacie *Ustawienia → Panel administratora*. Backend sprawdza grupę przy każdym zapytaniu `/api/admin/*` (bez niej 403).

- **Wyłącznik czatu** — na górze zakładki *Limity*: jednym przyciskiem (z potwierdzeniem) blokuje pytania wszystkim, także adminom, np. gdy model źle odpowiada; opcjonalny komunikat dla użytkowników (do 300 znaków). Wyłączony czat: `/chat` i `/chat/stream` zwracają `503` (`chat_disabled`) zanim zostanie zużyty limit czy wywołany model, a nad polem pytania pojawia się baner; historia, oceny i panel działają dalej. Kto przełączył, trafia do logu backendu.
- **Limity** — globalny dzienny limit pytań na osobę (domyślnie `CHAT_DAILY_LIMIT=10`) i wyjątki per osoba: własny limit, bez limitu albo 0 (zablokowana), z notatką. Admini nie są zwolnieni z limitu — mogą nadać wyjątek sobie. Doba kończy się o północy czasu polskiego. Liczy się każde pytanie, które dochodzi do modelu (także regeneracja i ponowienie); pytanie wraca do puli tylko po błędzie po stronie serwera (błąd modelu, pusta odpowiedź, nieudany zapis), a rozłączenie lub przerwanie przez użytkownika (Stop, zamknięcie karty) w dowolnym momencie liczy się jak pytanie. Po wyczerpaniu limitu `/chat` i `/chat/stream` zwracają `429` (`rate_limited`, `reset_at`, nagłówek `Retry-After`), a użytkownik widzi komunikat z godziną odnowienia; stan zwraca `GET /api/usage`. Tu są też limity załączników (rozmiar pliku, plików w wiadomości, załączników dziennie — 0 wyłącza załączniki, typy plików); patrz sekcja *Załączniki*.
- **Zgłoszenia** — zgłoszone odpowiedzi z kopią pytania, odpowiedzi i źródeł; rozwiązanie / odrzucenie z notatką, eksport CSV.
- **Incydenty** — próby obejścia promptu z danymi osoby i dopasowanymi regułami.
- **Blokady** — osoby zablokowane po 3 ostrzeżeniach (od kiedy) i osoby z ostrzeżeniami poniżej limitu (ile, ostatnie ostrzeżenie); przycisk *Odblokuj* / *Wyzeruj ostrzeżenia* (z potwierdzeniem) zdejmuje blokadę i zeruje licznik — liczą się odtąd tylko nowe incydenty, stare zostają na liście incydentów. `/api/admin/blocks`.
- **Diagnostyka** — dostawca i model, czas działania, statystyki wywołań modelu od startu (błędy, średni czas i p95, ostatni błąd), pytania i aktywni użytkownicy (dziś / 7 dni), liczba kont, rozmów i wiadomości, otwarte zgłoszenia i incydenty, rozmiar indeksu RAG i data ostatniego ingestu, rozmiar bazy i wolne miejsce na dysku.

Wartości z `.env` (`CHAT_DAILY_LIMIT`, `ATTACHMENT_*`) są domyślne — zmiana w panelu zapisuje się w bazie (tabela `app_settings`) i ma pierwszeństwo. Dzienne liczniki starsze niż 90 dni są kasowane w tle.

## Załączniki

Spinacz w polu pytania, przeciągnięcie pliku na czat albo wklejenie obrazu. Plik wysyła się od razu (`POST /api/attachments`, surowe ciało, nazwa w nagłówku `X-Filename`), a pytanie wskazuje go przez `attachment_ids`. Wysłane pliki widać pod pytaniem (kliknięcie pobiera, `GET /api/attachments/{id}` — tylko właściciel); niewysłany można usunąć (`DELETE`).

- **Typy i limity** — PDF, DOCX, TXT, PNG, JPEG, WEBP; domyślnie do 10 MB na plik (obrazy do 5 MB), 5 plików w pytaniu i 20 plików na osobę na dobę (`ATTACHMENT_*`, panel administratora). Typ jest rozpoznawany po zawartości pliku, nie po rozszerzeniu. Limit dzienny liczy każdą próbę wysłania — także plik odrzucony z własnej winy (za duży, zły typ, nieczytelny, wysyłany dłużej niż 120 s) i przerwany przez klienta; miejsce wraca tylko po błędzie serwera. Po wyczerpaniu: `429` `attachments_limited`.
- **Ochrona przed nadużyciem** — najwyżej 2 wysyłania naraz na osobę (`429 uploads_busy`; frontend sam kolejkuje), niewysłane pliki jednej osoby razem najwyżej *pliki w wiadomości × MB na plik* (`429 attachments_storage_full`), a przy mniej niż 500 MB wolnego miejsca na wolumenie `507 storage_unavailable`. PDF jest czytany w osobnym procesie z twardym limitem czasu (40 s, potem kill) i na Linuksie limitem pamięci 1 GB; DOCX — liniowym skanerem, a archiwum zip z ogromnym spisem treści jest odrzucane przed jego wczytaniem.
- **Treść dla modelu** — tekst jest wyciągany raz, przy wysyłaniu (PDF: do 100 stron, zaszyfrowany/uszkodzony → `422 unreadable_file`; DOCX: bez nowych zależności, z ochroną przed zip bombami; do 60 tys. znaków na plik) i trafia do wiadomości jako blok *ZAŁĄCZNIKI UŻYTKOWNIKA* po bloku *KONTEKST* (razem do 40 tys. znaków, dzielone sprawiedliwie między pliki). Heurystyka prób obejścia promptu sprawdza też treść plików (reguły z prefiksem `attachment:` w incydentach).
- **Skany (OCR)** — strony PDF bez warstwy tekstowej są rozpoznawane Tesseractem (wbudowanym w PyMuPDF; języki `pol+eng`, 200 dpi, do 20 stron na plik, wtedy limit czasu 120 s). Obraz Dockera instaluje `tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng` i ustawia `TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata`. Bez danych Tesseracta (np. lokalnie na Windows) skan nie ma tekstu, a backend loguje to raz. Model dostaje w nagłówku pliku ostrzeżenie, że tekst z OCR może zawierać błędy.
- **Wcześniejsze pliki rozmowy** — każde kolejne pytanie (i regeneracja) dostaje też pliki wysłane wcześniej w tej rozmowie: po plikach bieżącego pytania, od najnowszych, oznaczone „wcześniej w rozmowie”. Pliki bieżącego pytania mają pierwszeństwo we wspólnym budżecie znaków; wcześniejsze, które się nie mieszczą, są pomijane z notką. Wcześniejsze obrazy idą tylko do modeli z obsługą obrazów (najwyżej 3 najnowsze, łącznie z obrazami bieżącego pytania do 15 MB); dla pozostałych są pomijane bez błędu. Nad polem pytania widać, ile takich plików ma rozmowa.
- **Obrazy** — tylko dla dostawców z obsługą obrazów: `claude`, `openrouter`, `ollama` (wybrany model musi je obsługiwać, inaczej błąd modelu). Przy `cursor` pytanie z obrazem dołączonym do tego pytania dostaje `422 images_unsupported`.
- **Zasada „najpierw odpowiedź”** — plik jest przypinany do pytania dopiero po zapisaniu odpowiedzi; błąd modelu zostawia go niewysłanym (można ponowić). Regeneracja odpowiedzi używa plików powtarzanego pytania.
- **Retencja** (mało miejsca na dysku) — pliki znikają razem z rozmową (usunięcie, wygaśnięcie po `CHAT_HISTORY_RETENTION_DAYS`, wypchnięcie przez limit rozmów); niewysłane po 24 h (zadanie w tle).
- **Pliki na dysku** — katalog `ATTACHMENTS_DIR` (domyślnie `uploads`, w Dockerze wolumen `chatbot-uploads`), losowe nazwy. Nginx we froncie przepuszcza do 51 MB tylko dla `/api/attachments`; jeśli przed nim stoi kolejny reverse proxy (VM KSI), też potrzebuje `client_max_body_size` co najmniej równego limitowi plików.

## Motywy okazjonalne (ksi.sh)

Czat zmienia wygląd razem ze stroną główną KSI, która ma motywy okazjonalne (konkurs odznak KSI). **O tym, czy i jaki motyw trwa, decyduje wyłącznie ksi.sh** — w repozytorium nie ma żadnych motywów, terminów ani grafik i nie wolno ich tu dodawać (repo jest publiczne, a ujawnienie motywów przed czasem psuje konkurs). Odznaki odbiera się tylko na ksi.sh; czat nie ma do tego przycisku.

- **Skąd stan** — backend w tle co `OCCASION_REFRESH_SECONDS` (domyślnie 60 s) pyta API ksi.sh (`/api/occasion` z tokenem `OCCASION_API_TOKEN`, sekret tylko w `.env`), która okazja trwa i kiedy się kończy — motyw znika dokładnie w chwili końca. API nie podaje kolorów ani fasady, więc przy trwającej okazji backend czyta też `OCCASION_SOURCE_URL` (domyślnie `https://ksi.sh/`); motyw jest widoczny, gdy strona pokazuje tę samą okazję co API. Terminy z API zostają w backendzie (nie ma ich w odpowiedziach ani w logach). Bez tokenu albo gdy API nie odpowiada, o motywie decyduje sama strona: atrybuty `<html data-occasion data-color>`, blok kolorów `:root { --color-night-*; --color-accent* }` i fasadę z modułu okazji (`/assets/*.js` → `/assets/*.svg`). To odczyt cudzej, zminifikowanej strony, więc wszystko jest sprawdzane wzorcami; coś nierozpoznanego daje „brak fasady” albo „brak motywu”, nigdy błąd czatu. Gdy ksi.sh nie odpowiada, zostaje ostatni stan, najwyżej przez 30 minut. `OCCASION_SOURCE_URL=off` wyłącza funkcję.
- **API** — `GET /api/occasion` (publiczne, także dla ekranu logowania): `{active, dark, theme_color, palette, facade: {pl, en}}`, bez nazwy i terminów okazji; `503 occasion_unknown` tylko tuż po starcie. `GET /api/occasion/facade/{wersja}?scheme=light|dark` podaje fasadę bieżącej okazji: SVG jest przed podaniem sprawdzany (tylko elementy grafiki z listy, bez skryptów, zdarzeń, linków i zewnętrznych zasobów) i ma własne CSP bez skryptów — dlatego w `nginx.conf` ma osobny `location`.
- **Wygląd** — motyw z `data-color` (ksi.sh przełącza się wtedy na ciemny) wymusza ciemny motyw czatu niezależnie od ustawienia „jasny/systemowy”; jego paleta podmienia ciemne kolory (tekst i przyciski tylko przy kontraście WCAG AA). Fasada jest na ekranie logowania i na dole nowej, pustej rozmowy. Użytkownik może wyłączyć motywy w Ustawienia → Motyw → „Motywy okazjonalne”. Ostatni stan jest w `localStorage` (`chatOccasion`, ważny 12 h), żeby po przeładowaniu nie było mignięcia (`public/theme-init.js`).

## Autorzy

Mentor: Oliwier Polak ([@Kangurur](https://github.com/Kangurur))

- Karol Dziekan ([@Dariooo23](https://github.com/Dariooo23))
- Patrycja Jaworska ([@zazu1023](https://github.com/zazu1023))
- Sonia Skuczeń ([@SonSku](https://github.com/SonSku))
- Mikołaj Suchan ([@Wuchan33](https://github.com/Wuchan33))
- Aleksandra Woźny ([@olkaa566](https://github.com/olkaa566))
