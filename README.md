<h1 align="center">Chatbot Wydziałowy UJ – Wydział Matematyki i Informatyki</h1>

<p align="center">
  Chatbot oparty o RAG, który odpowiada na pytania studentów i kandydatów dotyczące Wydziału Matematyki i Informatyki UJ.
  <br>Tworzony przez Koło Naukowe KSI.
</p>

<p align="center">
    <img src="https://img.shields.io/badge/status-w%20budowie-yellow">
    <img src="https://img.shields.io/badge/python-3.11+-blue">
    <img src="https://img.shields.io/badge/license-TODO-lightgrey">
  </p>

---

## Spis treści

- [O projekcie](#o-projekcie)
- [Dlaczego ten projekt powstał](#dlaczego-ten-projekt-powstał)
- [Architektura](#architektura)
- [Uruchomienie przez Docker](#uruchomienie-przez-docker)
- [Instalacja](#instalacja)
- [Użycie](#użycie)
- [Struktura repozytorium](#struktura-repozytorium)
- [Zespół](#zespół)
- [Roadmapa](#roadmapa)
- [Licencja](#licencja)

---

## Wersje językowe / Language Versions

- **Polski** — ten dokument
- [English Version](README.en.md)

---

## O projekcie

Projekt realizowany w ramach **Koła Naukowego Studentów Informatyki (KSI)** przy Wydziale Matematyki i Informatyki Uniwersytetu Jagiellońskiego (UJ WMI). Celem projektu jest stworzenie dedykowanego chatbota wykorzystującego architekturę **RAG (Retrieval-Augmented Generation)**, który sprawnie odpowiada na pytania związane z wydziałem, bazując na sprawdzonych dokumentach i danych źródłowych.

> _Projekt znajduje się w fazie rozwoju. Niektóre funkcjonalności są w trakcie wdrażania._

**TODO (opcjonalnie):** jakieś przykłady pytań

## Dlaczego ten projekt powstał

Nasz projekt powstał z potrzeby ułatwienia życia studentom (szczególnie tym zaczynającym swoją przygodę na WMI) oraz stworzenia realnego, zaawansowanego narzędzia inżynierskiego w ramach Koła Naukowego Studentów Informatyki (KSI). Chcieliśmy połączyć teorię z praktyką:

- Wykorzystać architekturę RAG (Retrieval-Augmented Generation) do przeszukiwania realnych, wydziałowych baz danych i stron.
- Zbudować w pełni lokalny ekosystem AI (oparty m.in. o model Qwen).
- Stworzyć scentralizowanego, inteligentnego asystenta, który w kilka sekund odpowie na pytania o przedmioty, zasady zaliczeń czy materiały z koła, eliminując konieczność przeklikiwania dziesiątek podstron.

## Architektura

System opiera się na nowoczesnym stosie technologicznym dla systemów RAG:

- **LLM (Decoder):** Model `Qwen3-30B-A3B Q4_K_M` hostowany lokalnie.
- **Embeddings / Baza Danych:** (TODO: uzupełnić).
- **Przetwarzanie dokumentów:** `pymupdf4llm`, `BeautifulSoup4`, `pypdf`, `python-docx`.
- **Backend:** Python, (TODO: uzupełnić).

## Uruchomienie przez Docker

Najprostszy sposób na odpalenie całej aplikacji (frontend + backend + RAG + lokalny LLM) bez ręcznej instalacji zależności.

### Wymagania

- [Docker](https://docs.docker.com/engine/install/) + **Docker Compose v2** (polecenie `docker compose`, nie stary `docker-compose`) - w praktyce każda aktualna instalacja Dockera już to ma.
- GPU NVIDIA + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) - żeby Ollama (LLM) i embeddingi RAG-a liczyły się na GPU, a nie na CPU (Qwen 14B na samym CPU jest w praktyce nieużywalny).

### Kroki

```bash
# 1. Skonfiguruj zmienne środowiskowe (klucze USOS opcjonalne - potrzebne tylko do scrapowania)
cp .env.example .env

# 2. Zbuduj obrazy i odpal caly stack
docker compose up --build
```

Przy pierwszym uruchomieniu kontener `ollama-pull` pobierze model `qwen2.5:14b` (kilka GB) zanim wystartuje backend - to jest normalne i jednorazowe (model zostaje w wolumenie `ollama-data`).

Po starcie:

- Frontend: http://localhost:8080
- Backend (bezpośrednio, opcjonalnie do debugowania): http://localhost:8000/health

Frontend rozmawia z backendem przez wbudowany reverse-proxy nginksa (`/api/*`), więc appka działa spod dowolnego adresu, na którym wystawisz serwer - nie trzeba niczego przebudowywać pod konkretny host.

Inny model Ollamy lub inny port frontendu na hoście: ustaw `OLLAMA_MODEL=` / `FRONTEND_PORT=` w `.env` przed `docker compose up`.

**Poza zakresem obecnego docker-compose** (na razie uruchamiane ręcznie, poza kontenerami - patrz [Użycie](#użycie)): scrapery (`src/data/`) i pipeline ingestu RAG (`src/backend/RAG/ingest/run_ingest.py`) - to są jednorazowe/okazjonalne zadania wsadowe, nie długo działające serwisy.

## Instalacja

**TODO:** projekt jest w trakcie budowy, więc pełna instrukcja instalacji end-to-end jeszcze nie istnieje. Poniżej szkielet do uzupełnienia w miarę powstawania poszczególnych modułów.

### Wymagania

- Python 3.11+
- **TODO:** reszta wymagań

### Kroki

```bash
# 1. Sklonuj repozytorium
git clone <TODO-adres-repo>
cd <TODO-nazwa-repo>

# 2. Utwórz środowisko wirtualne
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Zainstaluj zależności
pip install -r requirements.txt
# TODO: zrobić requirements.txt obejmujące cały projekt

# 4. Skonfiguruj zmienne środowiskowe
cp .env.example .env   # TODO: dodać plik .env.example
# uzupełnij m.in. MORDOR_COOKIE, dane USOS API
```

## Użycie

Po skonfigurowaniu środowiska (patrz [Instalacja](#instalacja)):

```bash
# Pobranie danych ze stron wydziałowych i Wikipedii
python src/data/strony/scraper.py

# Pobranie plików z Mordoru
python src/data/mordor/files_downloader.py

# Przetworzenie pobranych plików z Mordoru na chunki (do bazy wektorowej)
python src/data/mordor/mordor_scraper.py

# Zapytania do USOS API (tryb eksploracyjny/anonimowy)
python src/data/usos/usos_client.py services/fac/fac2 --params fac_id=WMI

# TODO: uzupełnić przy następnych krokach
```

## Struktura repozytorium

```
.
├── docs/
│   └── plan.txt              # plan projektu, notatki ze sprintów
├── src/
│   ├── backend/
│   │   └── main.py           # API backendu (FastAPI) — w budowie
│   └── data/
│       ├── mordor/           # pobieranie i przetwarzanie plików z Mordoru
│       ├── strony/           # scraper stron wydziałowych, kół, Wikipedii
│       └── usos/             # klient USOS API
├── README.md
└── README.en.md
```

**TODO:** rozbudować opis w miarę powstawania kolejnych katalogów

## Zespół

**Mentor:** Oliwier Polak (@Kangurur)

**Członkowie zespołu:**

- **Karol Dziekan** (@Dariooo23)
- **Patrycja Jaworska** (@zazu1023)
- **Sonia Skuczeń** (@SonSku)
- **Mikołaj Suchan** (@Wuchan33)
- **Aleksandra Woźny** (@olkaa566)

## Roadmapa

**Must have**

- RAG (encoder + baza danych + decoder)
- Dane

**Should have**

- Prosta strona

**Could have**

- Ładna strona
- Zaawansowane funkcjonalności
- Konta użytkowników itp.
- Automatyzacja

**TODO:** zamienić na aktualną roadmapę / link do tablicy projektowej, gdy plan się rozwinie.

## Licencja

**TODO:** projekt nie ma jeszcze wybranej licencji.
