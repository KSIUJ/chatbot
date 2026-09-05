# Postawienie projektu lokalnie (bez Dockera)

Uruchomienie backendu (FastAPI + RAG) i frontendu (Vite/React) wprost na
hoście, w trybie developerskim. Dla wersji kontenerowej (`docker compose`)
patrz [DOCKER.md](DOCKER.md) — ten dokument opisuje flow „gołe" venv +
`npm run dev`, oraz **scraping i ingest danych RAG**, do których DOCKER.md
się odwołuje.

---

## 1. Wymagania

| Narzędzie | Wersja | Uwagi |
|---|---|---|
| Python | **3.12** | Na 3.13/3.14 część wheeli (chromadb, torch) potrafi nie wejść. |
| Node.js | **20+** (LTS 22 zalecane) | Vite 8. Obraz Dockera frontendu używa `node:20`. |
| Git | dowolny nowszy | |
| Miejsce na dysku | ~3–4 GB | `pip install` ciągnie `torch` (CPU) przez `sentence-transformers` + model embeddingowy `sdadas/mmlw-roberta-large` (~1.5 GB z HuggingFace przy pierwszym użyciu). |

Opcjonalnie `HF_TOKEN` w środowisku — bez niego pobieranie modelu z HF idzie
jako unauthenticated (wolniej, rate limity).

---

## 2. Kod

```bash
git clone https://github.com/KSIUJ/chatbot.git
cd chatbot
git checkout docker-full-setup   # albo main, jeśli praca została już zmergowana
```

---

## 3. Backend — środowisko Python

Z katalogu głównego repo:

```bash
python -m venv .venv
# Windows PowerShell:      .venv\Scripts\Activate.ps1
# Windows Git Bash / cmd:  .venv\Scripts\activate
# Linux / macOS:           source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` obejmuje całość backendu: fastapi, uvicorn[standard],
anthropic, sentence-transformers, chromadb, langchain-text-splitters,
sqlalchemy, alembic, pymupdf4llm, requests, requests_oauthlib,
python-dotenv, pytest. Pierwsza instalacja jest długa (torch).

---

## 4. Frontend — zależności

```bash
cd src/frontend
npm install
cd ../..
```

Frontend woła backend pod `import.meta.env.VITE_API_URL` z fallbackiem na
`http://127.0.0.1:8000` (patrz `src/frontend/src/lib/api.ts`). W trybie
`npm run dev` fallback wystarcza — backend musi stać na porcie **8000**.

---

## 5. `.env`

Utwórz `.env` w katalogu głównym repo (jest w `.gitignore` — nie commitować).
Wzór wszystkich pól z komentarzami: `.env.example`. Minimalny zestaw zależy od
wybranego dostawcy LLM (`LLM_PROVIDER`):

```env
# domyślnie "ollama"; do dema najprościej hostowany dostawca:
LLM_PROVIDER=cursor
CURSOR_API_KEY=<z https://cursor.com/dashboard/api>
CURSOR_MODEL=claude-sonnet-5

# tylko jeśli będziesz od nowa scrapować USOS (rozdział 6):
USOS_CONSUMER_KEY=<z https://apps.usos.uj.edu.pl/developers/>
USOS_CONSUMER_SECRET=<j.w.>
```

Dostawcy LLM (`LLM_PROVIDER`, obsługa w `src/backend/llm/generate.py`):

| wartość | wymaga w `.env` | uwagi |
|---|---|---|
| `ollama` (domyślne) | — | lokalny model, wymaga uruchomionej Ollamy (`OLLAMA_MODEL`, domyślnie `qwen2.5:14b`) i `OLLAMA_NUM_CTX=8192` |
| `claude` | `ANTHROPIC_API_KEY` | najszybszy/najstabilniejszy do dema |
| `openrouter` | `OPENROUTER_API_KEY` | jedno API do wielu dostawców |
| `cursor` | `CURSOR_API_KEY` | Cursor Cloud Agents — **60–90 s na odpowiedź**, provisioning VM per zapytanie |

Po każdej zmianie `.env` zrestartuj backend — `load_dotenv()` czyta plik raz,
przy starcie procesu.

---

## 6. Dane i baza wektorowa

Katalogi `data/` (surowe scrapy) i `dataset/` (Chroma + indeks FTS5) są w
`.gitignore` — **nie ma ich w repo**. Bez nich RAG nie ma z czego odpowiadać
(chatbot wystartuje, ale „nic nie wie" o wydziale). Wybierz wariant:

### Wariant A — skopiuj gotowe dane (szybko)

Z maszyny, która już ma zescrapowane i zingestowane dane, skopiuj do tego
samego miejsca w repo:

```
data/strony/webiste_data.txt          (~740 KB)
data/usos/staff/staff_*.json          (~300 KB)
dataset/vectorstore/                   (~28 MB, cała zawartość)
dataset/lexical.db                     (~2 MB)
```

Jeśli skopiujesz `dataset/` w całości — **pomijasz rozdział 7** (ingest już
zrobiony). Model embeddingowy i tak dociągnie się z HF przy pierwszym
zapytaniu.

### Wariant B — zbuduj od zera (bez Mordoru)

Scraper stron potrzebuje dodatkowych paczek (nie ma ich w głównym
`requirements.txt`):

```bash
pip install -r src/data/strony/requirements.txt   # beautifulsoup4, pypdf, python-docx
```

Scrape:

```bash
# strony wydziałowe + koła + Wikipedia -> data/strony/webiste_data.txt
python src/data/strony/scraper.py

# pracownicy z USOS API -> data/usos/staff/staff_UJ.WMI_<timestamp>.json
#   wymaga USOS_CONSUMER_KEY / USOS_CONSUMER_SECRET w .env
cd src/data/usos && python scrape_staff.py && cd ../..
```

**Mordoru nie ruszamy** — `from_mordor` zostaje poza ingestem (rozdział 7).

---

## 7. Ingest do bazy wektorowej

Pomiń, jeśli w wariancie A skopiowałeś pełne `dataset/`. Z katalogu głównego
repo:

```bash
# Windows PowerShell:
$env:PYTHONUTF8=1; python -m src.backend.RAG.ingest.run_ingest --source strony --source usos --purge
# Linux / macOS / Git Bash:
PYTHONUTF8=1 python -m src.backend.RAG.ingest.run_ingest --source strony --source usos --purge
```

- `--source strony --source usos` — **bez `mordor`**.
- `--purge` — czyści te źródła z Chroma i z indeksu FTS5 przed ponownym
  zapisem; bez tego `filter_new` pomija już zapisane rekordy → no-op.
- `PYTHONUTF8=1` — bez tego polskie znaki w pipeline potrafią się psuć
  (mojibake) na Windowsie.

Weryfikacja liczności (oba indeksy powinny się zgadzać):

```bash
python -c "import sys; sys.path.insert(0,'src'); from backend.RAG.vectorstore import VectorStore; c=VectorStore().collection; print({s: len(c.get(where={'source':s})['ids']) for s in ['mordor','strony','usos']}, 'total', c.count())"
```

Stan referencyjny: `{'mordor': 0, 'strony': 991, 'usos': 208} total 1199`.

---

## 8. Baza aplikacji (users / konwersacje)

SQLite (`chatbot.db`) tworzy się sam przy starcie backendu — `init_db()` w
`src/backend/database.py` woła `Base.metadata.create_all()`. Nic nie trzeba
robić.

Migracja Alembic (`alembic/versions/`) istnieje i jest używana w obrazie
Dockera (`entrypoint.sh` robi `alembic upgrade head`), ale do lokalnego
SQLite nie jest potrzebna. Dla Postgresa: ustaw `DATABASE_URL` w `.env` i
uruchom `alembic upgrade head`.

---

## 9. Uruchomienie

Dwa terminale, oba z katalogu głównego repo, z aktywnym venv.

**Backend (port 8000, wymagany):**

```bash
# Windows PowerShell:
$env:PYTHONUTF8=1; $env:PYTHONIOENCODING="utf-8"; python -m uvicorn backend.main:app --app-dir src --host 127.0.0.1 --port 8000
# Linux / macOS / Git Bash:
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python -m uvicorn backend.main:app --app-dir src --host 127.0.0.1 --port 8000
```

Pierwszy start dociąga model `sdadas/mmlw-roberta-large` z HuggingFace
(~1.5 GB) — potem jest w cache.

**Frontend (port 5173):**

```bash
cd src/frontend
npm run dev
```

Otwórz **http://localhost:5173**.

---

## 10. Weryfikacja

```bash
# 1. testy — powinny przejść wszystkie
python -m pytest tests -q            # oczekiwane: 81 passed

# 2. health backendu
curl http://127.0.0.1:8000/health   # {"status":"ok"}

# 3. retrieval bez LLM (szybkie po załadowaniu encodera)
python -c "import sys; sys.path.insert(0,'src'); from backend.RAG.context_builder import build_context; ctx,files=build_context('jakie sa zasady wpisu warunkowego na kolejny rok', k_mordor=0, k_other=4); print(ctx[:400])"

# 4. pełny /chat end-to-end (z Cursorem ~60-90 s na odpowiedź!)
curl -s --max-time 300 -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Jakie sa zasady wpisu warunkowego na kolejny rok?"}'
```

Poprawna odpowiedź na (3)/(4): fragmenty z `matinf.uj.edu.pl` z URL-ami źródeł,
polskie znaki bez mojibake, wzmianka o progu **50 ECTS**.

---

## 11. Znane pułapki

| Objaw | Przyczyna / fix |
|---|---|
| `ModuleNotFoundError: fastapi` przy pytest | uruchamiasz systemowym Pythonem zamiast venv. Aktywuj venv lub użyj `.venv/Scripts/python.exe -m pytest`. |
| Mojibake w odpowiedziach (`mogę` → `mogÄ™`) | brak `PYTHONUTF8=1` przy backendzie / ingescie (Windows). |
| `/chat` trwa 60–90 s | `LLM_PROVIDER=cursor` — Cursor Cloud Agents provisionuje VM na każde zapytanie. Przełącz na `claude` dla szybkości. |
| Frontend nie łączy się z API | backend nie stoi na 8000 albo nie wystartował. |
| `run_ingest` nic nie robi | brak `--purge` — rekordy już są w bazie, `filter_new` je pomija. |
| Zmiana w `.env` nie działa | `load_dotenv()` czyta plik raz przy imporcie. Zrestartuj backend po każdej edycji `.env`. |
| Wolne / rate-limitowane pobieranie modelu HF | ustaw `HF_TOKEN` w środowisku. |
