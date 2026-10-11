# Format zbiorów danych RAG-a

Kontrakt między scraperami (`pipeline/scrapers/`) a RAG-iem: co scraper ma
zapisać w `data/<źródło>/`, żeby ingest (`python -m pipeline.ingest.run_ingest`)
mógł to zaindeksować. RAG nie zna scraperów — zna tylko ten format.
Schematy JSON (dla scraperów w dowolnym języku): `docs/datasets/*.schema.json`,
generowane z modeli (`python -m src.backend.rag.datasets_cli schemas --out docs/datasets`).

## Wspólne zasady

```
data/<źródło>/
  manifest.json      opis zbioru
  records.jsonl      rekordy, jeden obiekt JSON na linię (może być kilka plików)
  ...                pliki źródła, jeśli potrzebne (np. skany Mordoru)
```

`manifest.json`:

| pole | znaczenie |
|---|---|
| `source` | nazwa źródła, taka jak katalog (`uj_pages`, `usos`, `mordor`, `ksi`) |
| `format_version` | wersja tego formatu — obecnie `1` |
| `collected_at` | kiedy dane zebrano, ISO 8601 ze strefą (`2026-10-11T08:00:00Z`) |
| `collector` | kto zebrał: scraper i wersja (np. `pipeline/scrapers/usos@abc1234`) |
| `files` | pliki z rekordami, ścieżki względne `.jsonl` wewnątrz katalogu |

Każdy rekord ma tę samą kopertę:

| pole | znaczenie |
|---|---|
| `id` | **stały** identyfikator w obrębie źródła (adres, id z USOS, ścieżka pliku) — ten sam obiekt przy kolejnym przebiegu ma to samo `id` |
| `kind` | rodzaj rekordu, wartości zależą od źródła |
| `title` | tytuł strony / imię i nazwisko / nazwa pliku |
| `url` | adres http(s), jeśli obiekt ma stronę |
| `lang` | język treści (`pl`, `en`), opcjonalnie |
| `updated_at` | data zmiany w źródle (ISO 8601 ze strefą), jeśli źródło ją podaje |
| `content` | treść w **Markdownie**: nagłówki `#`, listy, tabele — struktura strony ma zostać zachowana (nagłówki dzielą tekst na fragmenty) |
| `attributes` | pola własne źródła, poniżej |

Jak rekord trafia do indeksu: `content` jest dzielony nagłówkami (`#`, `##`,
`###`) na sekcje, małe sąsiednie sekcje są łączone, duże dzielone na
fragmenty po ok. 1000 znaków (`core/chunking.py`). Każdy fragment zaczyna się
linią kontekstu, np. `O nas › Biblioteka › Godziny otwarcia` (okruszki,
tytuł, ścieżka nagłówków) — ta linia jest wyszukiwana (także jako tytuł
w BM25) i widzi ją model. Dlatego `title`, nagłówki w `content`
i `breadcrumbs` warto wypełniać: bez nich fragment strony nie mówi, czego
dotyczy.

Nieznane pola są błędem (literówka nie przejdzie po cichu). Ingest odrzuca
cały zbiór z komunikatem `plik:linia: pole: błąd`; sprawdzenie bez ingestu:
`python -m src.backend.rag.datasets_cli check`.

## `uj_pages` — strony UJ

Wydział, USOSownia, koła naukowe, pozostałe strony UJ, Wikipedia. Strony KSI
idą do `ksi` (ten sam format).

- `kind`: `page` (strona HTML) albo `document` (plik pdf/docx/... ze strony)
- `url`: wymagany; `id`: zwykle ten sam adres
- `content`: treść strony bez menu, stopki i elementów nawigacji, z nagłówkami
- `attributes`:
  - `site` — host, np. `matinf.uj.edu.pl`
  - `category` — `faculty` (wydział), `uj`, `usosownia`, `student_group`, `ksi`, `wikipedia`, `other`
  - `breadcrumbs` — ścieżka w menu witryny, np. `["Studenci", "Formularze wniosków"]`
  - `media_type` — `text/html` dla stron, typ pliku dla dokumentów

## `usos` — pracownicy

- `kind`: `staff`; `id`: id osoby w USOS; `title`: imię i nazwisko; `url`: profil w USOSweb
- `content`: pusty — wszystko jest w `attributes`
- `attributes`: `usos_id`, `first_name`, `last_name`, `titles_before`
  (`dr hab.`), `titles_after` (`prof. UJ`), `positions` (lista
  `{name, unit}`), `room` (`{number, building}` albo `null`),
  `office_hours` i `interests` (zwykły tekst, bez HTML-a), `email`,
  `phones` (lista), `homepage_url`

## `mordor` — materiały studenckie

Pliki leżą w `data/mordor/` w strukturze katalogów Mordoru, rekordy obok nich.

- `kind`: `text` (jest tekst — z warstwy tekstu pliku albo z OCR skanu),
  `scan` (pdf bez tekstu, którego OCR nie odczytał), `image` (jpg/png);
  `id`: ścieżka pliku; `title`: nazwa pliku
- `content`: tekst pliku w Markdownie (dla `text`; przy `pages` — strony
  połączone w całość)
- `attributes`:
  - `path` — ścieżka pliku względem `data/mordor/`, z `/`
  - `file_type` — rozszerzenie bez kropki
  - `course`, `academic_year` (`2024/25`), `material_kind` (egzamin, kolokwium,
    rozwiązania, zadania, notatki, wykład, ćwiczenia, ...; kilka po przecinku)
    — puste, gdy nieznane; trafiają do linii kontekstu fragmentów
  - `pages` — tekst strona po stronie (`{number, text, ocr}`), gdy jest;
    `ocr: true` dla tekstu odczytanego ze skanu. Gdy `pages` są, fragmenty
    powstają strona po stronie (z numerem strony w linii kontekstu), a
    `content` jest pomijany

## `ksi` — informacje o KSI

- strony KSI w `data/ksi/` — format jak `uj_pages`, `category: ksi`
- notatki pisane ręcznie w repozytorium: `knowledge/ksi/*.md` (opis w `knowledge/ksi/README.md`)

## Stare formaty scraperów

Do czasu przebudowy scraperów ich dotychczasowe wyjście
(`data/strony/website_data.txt`, `data/usos/staff/staff_*.json`, pliki
w `data/mordor/`) zamienia na ten format:

```bash
python -m src.backend.rag.datasets_cli convert
```

Adaptery są w `src/backend/rag/sources/<źródło>/legacy.py` i znikną, gdy
scrapery zaczną zapisywać ten format same. Czego stary format nie ma,
adaptery odgadują:

- strony: tytuł i okruszki z adresu (`/o-nas/biblioteka` → `["O nas",
  "Biblioteka"]`, polskie znaki odtwarzane ze słów na stronach), dla plików
  nazwa pliku, dla aktualności pierwsza linia treści
  (`sources/uj_pages/titles.py`); nagłówków stary crawler nie zapisuje
- Mordor: przedmiot, rok akademicki i rodzaj materiału ze ścieżki
  (`sources/mordor/paths.py`); skany są odczytywane OCR-em (Tesseract
  w PyMuPDF, `pol+eng`, do 40 stron na plik) — potrzebne dane językowe
  Tesseracta (są w obrazie backendu), bez nich skany zostają `scan`
