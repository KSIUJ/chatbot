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
