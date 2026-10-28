# Plan rozbudowy chatbota KSI

Stan na 2026-10-27. Cztery kolejne duże gałęzie: **Mordor**, **strony UJ**,
**Microsoft Teams** i **Pegaz**. Dla każdej: co już jest, skąd dane i na jakich
zasadach wolno je brać, ocena wykonalności, ryzyka, architektura i przebieg
implementacji w PR-ach. Fakty o zewnętrznych systemach sprawdzone tego dnia
(robots.txt, publiczne konfiguracje, dokumentacja) — przed startem gałęzi
warto je sprawdzić jeszcze raz.

## Podsumowanie

| Gałąź | Co daje | Wykonalność | Bloker | Nakład |
|---|---|---|---|---|
| 1. Mordor | materiały studenckie (egzaminy, kolokwia, notatki) w odpowiedziach | **wysoka** | dostęp do danych Mordoru od jego opiekunów (usługa KSI) | średni–duży (OCR) |
| 2. Strony UJ | aktualne strony wydziału i UJ, dokumenty, regulaminy | **wysoka** | brak (część stron UJ zabrania robotów — omijamy je albo prosimy o zgodę) | średni |
| 3. Microsoft Teams | pliki zespołów przedmiotów, streszczenia kanałów, zadania | technicznie wysoka, **organizacyjnie niska** | zgoda administratora Microsoft 365 UJ (i prawdopodobnie IOD) | duży |
| 4. Pegaz | terminy zadań, kursy, oceny, materiały z Moodle | **zależna od DRiJK** | wyłączony mobilny web service Pegaza | mały (kalendarz iCal) / średni (API) |

**Rekomendowana kolejność:** od razu wysłać zapytania do IT UJ (Teams) i DRiJK
(Pegaz) — odpowiedzi zajmą tygodnie (szablony na końcu). W tym czasie
**strony UJ** (bez zależności zewnętrznych, poprawiają odpowiedzi wszystkim,
a obecne dane są z 2026-10-11) i równolegle **Mordor**, gdy tylko będzie
ustalony dostęp do jego danych. Potem Pegaz (najpierw kalendarz iCal) i Teams —
w kolejności, w jakiej przyjdą zgody.

## 0. Punkt wyjścia

### Co już jest i z czego korzystają nowe gałęzie

- **Format zbiorów i RAG** — `src/backend/rag/DATASETS.md` (umowa scraper ↔
  RAG), źródła w `src/backend/rag/sources/` (`uj_pages`, `mordor`, `usos`,
  `ksi`), wersjonowany indeks z `index sync` (atomowe przełączenie, backend
  podchwytuje nowy indeks sam). Źródło `mordor` i jego format (`MaterialRecord`
  z tekstem strona po stronie i flagą OCR) już istnieją — brakuje danych.
- **Wzorzec scrapera** — `pipeline/scrapers/usos/`: kolektory, zapis tylko
  tego, co zebrano, strażnik spadku liczby rekordów, rekordy niepobrane
  zostają z poprzedniego zbioru, ponowienia z backoffem, uczciwy User-Agent.
- **Wzorzec integracji z danymi osoby** — `src/backend/usos/` (PR #53–#61):
  OAuth, token zaszyfrowany i związany z kontem czatu, narzędzia modelu tylko
  do odczytu (`llm/tools.py`, Claude i OpenRouter), znacznik
  `messages.personal_data`, dane osoby nigdy we wspólnym indeksie RAG.
- **Odświeżanie i nadzór** — `refresh-usos.sh` z crona (co noc, w niedzielę
  z pracownikami), ostrzeżenie w panelu admina o nieświeżych danych
  (`MAX_DATA_AGE` w `src/backend/admin/diagnostics.py`).
- **Ewaluacja** — `rag_eval/` (wyszukiwanie, 149 pytań) i
  `rag_eval/usos_tools.py` (od pytania do odpowiedzi z narzędziami, 39 pytań,
  39/39).

### Wyniki wyszukiwania dziś (kopia indeksu produkcji, 2026-10-27)

| kategoria | pytań | @1 | @5 | w kontekście |
|---|---|---|---|---|
| wszystkie | 149 | 52% | 83% | 90% |
| staff | 30 | 100% | 100% | 100% |
| study | 28 | 54% | 93% | 93% |
| faculty | 15 | 80% | 93% | 93% |
| groups | 8 | 38% | 88% | 88% |
| followup | 10 | 60% | 90% | 90% |
| usos / usos_data | 14 / 16 | 0% / 25% | 71% / 94% | 100% / 100% |
| ksi | 8 | 12% | 12% | 62% |
| **mordor** | 6 | 0% | 0% | **0%** (brak danych) |

Nie znaleziono: study-14, study-21, faculty-04, groups-06, followup-02,
ksi-04/05/07 i wszystkie pytania `mordor`. To punkt odniesienia dla gałęzi 1 i 2.

### Zasady wspólne dla wszystkich gałęzi

1. **Tylko dane, które wolno brać.** `robots.txt` i regulaminy serwisów są
   wiążące — tak jak przy USOSowni (zamiast scrapera: własne poradniki
   z linkami). Bez podszywania się pod przeglądarkę i bez sesji użytkownika
   wyciągniętej z ciasteczek.
2. **Dane osoby zostają przy osobie.** Teams i Pegaz to dane konkretnego
   studenta: pobierane na bieżąco jego tokenem, tylko na jego pytanie, nigdy
   do wspólnego indeksu, odpowiedzi ze znacznikiem `personal_data` (bez kopii
   w ocenach i zgłoszeniach). Tylko odczyt, najmniejsze potrzebne uprawnienia.
3. **Sekrety** — tokeny zaszyfrowane (jak `usos/crypto.py`), nigdy w logach.
4. **Zmiany promptu** (nowe sekcje, zasady) — tylko po akceptacji właściciela
   repo.
5. **Ewaluacja przed wdrożeniem** — każda gałąź dokłada pytania do `rag_eval/`
   (dane wspólne) albo zestaw jak `usos_tools.jsonl` (dane osoby) i nie może
   pogorszyć pozostałych kategorii.
6. **Serwer** — VM 4 CPU bez AVX2, 8 GB RAM, bez GPU. Wszystko w kontenerach
   jako użytkownik `app` (pliki indeksu roota zatrzymują backend).

## 1. Mordor — materiały studenckie

### Stan

- Mordor to usługa KSI z materiałami studentów (egzaminy, kolokwia, notatki,
  rozwiązania). Adres `mordor.ksi.ii.uj.edu.pl` przekierowuje na
  **`https://mordor.ksi.sh/`**; zasoby wymagają logowania (`/file` →
  403 „Unauthorized”), `robots.txt` zabrania robotów (`Disallow: /`).
- Stary pobieracz `pipeline/scrapers/mordor/files_downloader.py` chodzi po
  HTML-u starego adresu z ciasteczkiem sesji (`MORDOR_COOKIE`) i pobiera pliki
  (pomija folder „książki”). Po zmianie adresu i logowania nie działa.
- Zbiór `data/mordor/` na produkcji jest **pusty** (0 rekordów), w ewaluacji
  `mordor` 0/6.
- Gotowe po stronie RAG: źródło `mordor`, format rekordów (`text` / `scan` /
  `image`, `pages` z flagą `ocr`, `course`, `academic_year`, `material_kind`),
  osobna pula w kontekście z nagłówkiem „MATERIAŁY STUDENCKIE (… mogą zawierać
  błędy lub być nieaktualne)”.

### Wykonalność: wysoka

Mordor należy do KSI, więc nie trzeba go scrapować — dostęp do danych
ustalamy z jego opiekunami. Do ustalenia przed startem:

1. **Jak Mordor trzyma pliki** (system plików, S3, baza) i czy ma API. Najlepiej
   eksport albo endpoint z listą plików (ścieżka, rozmiar, data zmiany, hash)
   i pobieraniem — z tokenem konta serwisowego, nie ciasteczkiem osoby.
2. **Kto ma dostęp do Mordoru** — czat jest tylko dla członków (grupa
   Keycloak). Jeśli Mordor ma węższą albo szerszą grupę, odpowiedzi czatu nie
   mogą udostępniać materiałów osobom, które w Mordorze ich nie widzą
   (ewentualnie: pula `mordor` tylko dla wybranej grupy).
3. **Zasady materiałów** — które foldery można włączyć (np. bez „książek” —
   prawa autorskie), czy skany z danymi osób (nazwiska na pracach) wolno
   indeksować.
4. **Wielkość** — liczba plików, GB, ile to skany bez tekstu (koszt OCR).

### Architektura

- `pipeline/scrapers/mordor/` od nowa, na wzór USOS: lista plików z API →
  pobieranie przyrostowe (tylko nowe i zmienione, po hashu) → ekstrakcja tekstu
  (`pypdf`, `python-docx`, txt) → **OCR skanów** (Tesseract `pol+eng` na CPU,
  wynik w pamięci podręcznej po hashu pliku, żeby każdy skan rozpoznawać raz)
  → metadane ze ścieżki (przedmiot, rok akademicki, rodzaj materiału) →
  rekordy `MaterialRecord` zgodne z `DATASETS.md`.
- **Powiązanie z USOS** — nazwy folderów przedmiotów mapowane na kody
  przedmiotów (`course:` w zbiorze USOS), żeby pytanie „kolokwia z Analizy 1”
  trafiało i w przedmiot, i w materiały.
- **OCR na tej VM** — Tesseract działa bez AVX2, ale wolno; pierwszy przebieg
  może trwać godziny. Opcje: przebieg nocny partiami, OCR na innej maszynie
  (np. laptop) z gotowym wynikiem kopiowanym na serwer, albo model z wizją
  tylko dla skanów bez tekstu (koszt API — oszacować na próbce).
- **Odświeżanie** — `refresh-mordor.sh` (wzór `refresh-usos.sh`) raz w tygodniu,
  `MAX_DATA_AGE["mordor"] = 8 dni` w ostrzeżeniach panelu.

### Przebieg (PR-y)

1. **Inwentaryzacja** — skrypt z listą plików i statystyką (liczby, typy,
   rozmiary, odsetek skanów); decyzje z punktów 2–4 wyżej.
2. **Kolektor i ekstrakcja tekstu** — zbiór bez OCR (pliki z warstwą tekstu),
   testy na atrapie API.
3. **OCR** z pamięcią podręczną i limitem czasu przebiegu.
4. **Metadane i powiązanie z przedmiotami USOS.**
5. **Odświeżanie z crona i ostrzeżenie w panelu.**
6. **Ewaluacja** — pytania `mordor` z 6 do ok. 20 (różne przedmioty, lata,
   rodzaje); cel: co najmniej 70% w kontekście bez spadku innych kategorii.

### Ryzyka

- Jakość OCR pisma ręcznego jest niska — skany notatek mogą być mało użyteczne
  (rekordy `scan` zostają, ale bez tekstu nie są wyszukiwane).
- Rozmiar indeksu i pamięć: każdy tysiąc stron to tysiące fragmentów;
  kontener ewaluacji mieści się dziś w ok. 2 GB — sprawdzić po pierwszym
  przebiegu.
- Uczciwość akademicka i prawa autorskie: czat cytuje rozwiązania egzaminów.
  Zasady promptu już traktują materiały jako studenckie i omylne; ewentualne
  dodatkowe ograniczenia — decyzja zarządu.

## 2. Strony UJ

### Stan

- Źródło `uj_pages`: **227 rekordów z 2026-10-11** (dane przeniesione ze
  starego formatu, `collector: legacy:uj_pages`): matinf.uj.edu.pl 206,
  kmsuj.matinf.uj.edu.pl 15, nkr.si 4, knmf.im.uj.edu.pl 1, Wikipedia 1;
  161 stron i 66 dokumentów, 1085 fragmentów w indeksie. Nie ma
  automatycznego odświeżania.
- Crawler `pipeline/scrapers/strony/scraper.py` **nie czyta `robots.txt`**
  (wykluczenia są wpisywane ręcznie), przedstawia się jako przeglądarka Chrome
  i zapisuje stary format tekstowy, który potem jest konwertowany.

### Na co pozwalają serwisy (`robots.txt`, 2026-10-27)

| Wolno (roboty dozwolone) | Nie wolno (`User-agent: *` / `Disallow: /`) |
|---|---|
| matinf.uj.edu.pl, tcs.uj.edu.pl, studia.uj.edu.pl, samorzad.uj.edu.pl, nkr.si, Wikipedia (przez API MediaWiki) | www.uj.edu.pl, **ii.uj.edu.pl, im.uj.edu.pl** (instytuty WMI), bip.uj.edu.pl, it.uj.edu.pl, biurokarier.uj.edu.pl, usosownia.uj.edu.pl |

Dla stron zabronionych: prośba o zgodę (instytuty ii/im to nasz wydział —
warto zapytać przez dziekanat albo administratorów stron), a do tego czasu
poradniki KSI z linkami, jak przy USOSowni.

### Wykonalność: wysoka

Bez zależności zewnętrznych; wzorzec scrapera USOS przenosi się prawie wprost.

### Architektura

- `pipeline/scrapers/uj_pages/` (zamiast `strony/`): kolektor na serwis
  (matinf, tcs, studia, samorząd, koła naukowe, Wikipedia przez API),
  wspólny `run.py` z zasadami jak w USOS (podmiana tylko tego, co zebrano,
  strażnik spadku, przeniesienie niepobranych).
- **Uprzejmy crawler** — `urllib.robotparser` dla każdego hosta (z `Crawl-delay`),
  User-Agent `KSI-chatbot-scraper/… (+https://chat.ksi.sh)`, mapa witryny
  (`sitemap.xml`) przed chodzeniem po linkach, limit stron na serwis.
- **Treść** — główna treść bez menu i stopki, nagłówki, ścieżka w menu
  (`breadcrumbs`), kategoria (`faculty` / `uj` / `student_group` / ...), daty
  modyfikacji; dokumenty pdf/docx z deduplikacją po hashu (ten sam regulamin
  podlinkowany z wielu stron to jeden rekord).
- **Przyrostowo** — `ETag` / `Last-Modified` / hash treści, żeby tygodniowy
  przebieg pobierał tylko zmiany.
- **Odświeżanie** — skrypt odświeżania uogólniony na źródła
  (`refresh-data.sh uj_pages|usos|mordor`), cron raz w tygodniu,
  `MAX_DATA_AGE["uj_pages"] = 8 dni`.

### Przebieg (PR-y)

1. **Rdzeń crawlera + matinf.uj.edu.pl** (robots, sitemap, ekstrakcja, zapis
   wprost w formacie `DATASETS.md`), porównanie z obecnym zbiorem.
2. **Pozostałe dozwolone serwisy + Wikipedia przez API.**
3. **Dokumenty** (pdf/docx, deduplikacja, limity rozmiaru).
4. **Odświeżanie z crona, ostrzeżenie w panelu, usunięcie `strony/`.**
5. **Ewaluacja** — pytania dla nowych serwisów (studia.uj.edu.pl, samorząd,
   tcs) i naprawa obecnych pudeł (study-14, study-21, faculty-04, groups-06,
   followup-02); bez spadku `faculty` (93%) i `study` (93%).

### Ryzyka

- Strony Liferay (matinf) mają dużo dublujących się adresów (parametry,
  wersje językowe) — normalizacja adresów, żeby indeks nie puchł.
- Szersze źródła = więcej szumu w kontekście; pilnować `hits_when_no_answer`
  w ewaluacji.

## 3. Microsoft Teams

### Stan i fakty

- UJ ma **jeden tenant Microsoft 365** (`eb0e26eb-bfbe-47d2-9e90-ebd2426dbceb`)
  dla `uj.edu.pl` i `student.uj.edu.pl`, konta zarządzane w chmurze (nie
  federacja). Przez niego loguje się też Pegaz.
- Dostęp do Teams daje **Microsoft Graph** (OAuth 2.0 w imieniu osoby,
  uprawnienia „delegated”).

### Co by się dało i jakich zgód to wymaga

| Funkcja | Uprawnienie Graph | Zgoda administratora |
|---|---|---|
| lista moich zespołów i kanałów | `Team.ReadBasic.All`, `Channel.ReadBasic.All` | nie |
| pliki zespołów przedmiotów (SharePoint) | `Files.Read.All` / `Sites.Read.All` | nie wg opisu uprawnień, ale **zablokowane dla zgody użytkownika** w domyślnej polityce Microsoftu od sierpnia 2025 |
| streszczenie postów z kanału przedmiotu | `ChannelMessage.Read.All` | **tak** |
| czaty | `Chat.Read` | nie wg opisu, **zablokowane** w domyślnej polityce od listopada 2025 |
| spotkania i nagrania / transkrypcje | `OnlineMeetings.Read`, `OnlineMeetingTranscript.Read.All` | zablokowane / **tak** |
| kalendarz | `Calendars.Read` | zablokowane w domyślnej polityce od listopada 2025 |
| zadania (Teams Assignments) | `EduAssignments.ReadBasic` | **tak** |

Wniosek: bez **zgody administratora tenanta UJ** da się co najwyżej wypisać
zespoły i kanały — każda użyteczna funkcja (pliki, posty, zadania, spotkania)
wymaga zatwierdzenia aplikacji przez IT UJ. Do tego tenant może mieć własną
politykę zgód (np. całkowity zakaz zgody użytkownika) — nie da się tego
sprawdzić z zewnątrz; rozstrzyga to próbna rejestracja aplikacji i ekran zgody.

### Wykonalność: technicznie wysoka, organizacyjnie niska

- **Bloker 1:** zgoda administratora M365 UJ na aplikację z wybranymi
  uprawnieniami (najlepiej ograniczona do potrzebnych, z weryfikacją wydawcy
  aplikacji).
- **Bloker 2:** ochrona danych — streszczenia kanałów i czatów to
  przetwarzanie wiadomości **innych osób** przez zewnętrzny model językowy.
  Prawdopodobnie potrzebna opinia Inspektora Ochrony Danych UJ i ocena
  skutków; bez niej zostają funkcje na własnych danych osoby (pliki, zadania).

### Architektura (po zgodzie)

- Rejestracja aplikacji w Entra ID, logowanie kodem autoryzacji z PKCE
  (MSAL, klient poufny), `offline_access` dla odświeżania tokenu.
- **Wspólne „połączone konta”** — uogólnienie `src/backend/usos/` (tabela
  połączeń, szyfrowanie, status i rozłączanie w Ustawieniach) na kilka
  dostawców: USOS, Microsoft, Pegaz. Robione przy drugiej integracji, nie
  wcześniej.
- Narzędzia modelu (tylko odczyt, limity jak w USOS): `teams_my_teams`,
  `teams_channel_files` (lista i treść pliku na żądanie, z limitem rozmiaru —
  ekstrakcja pdf/docx jak w scraperach), `teams_channel_digest` (posty od
  daty, przycięte, streszczane w odpowiedzi), `teams_my_assignments`.
- Graph ma limity zapytań (429 z `Retry-After`) — ponowienia jak w USOS.
- Nic nie trafia do wspólnego indeksu; odpowiedzi z `personal_data`.

### Przebieg

0. **Przed kodem:** zapytanie do IT UJ (szablon niżej) i próbna rejestracja
   aplikacji, żeby zobaczyć ekran zgody dla konta studenta.
1. Uogólnione połączone konta (refaktor USOS bez zmian zachowania).
2. Logowanie Microsoft + `teams_my_teams`.
3. Pliki zespołów.
4. Streszczenia kanałów (tylko po zgodzie IOD).
5. Zadania.
6. Ewaluacja od pytania do odpowiedzi (wzór `rag_eval/usos_tools.py`).

### Ryzyka

- Koszt: długie kanały to dużo tokenów — streszczenie z limitem dni i postów.
- Zakres: Teams kusi funkcjami zapisującymi (posty, pliki) — poza zakresem,
  tylko odczyt.

## 4. Pegaz (Moodle)

### Stan i fakty (publiczna konfiguracja aplikacji mobilnej, 2026-10-27)

- Pegaz (`pegaz.uj.edu.pl`) to **Moodle**, logowanie przez **OpenID Connect
  (Microsoft 365)**, wsparcie: DRiJK, `elearning@uj.edu.pl`.
- `enablewebservices: 1` — usługi sieciowe Moodle są włączone, ale
  **`enablemobilewebservice: 0`** — usługa mobilna (z której korzystają
  aplikacja Moodle i integracje użytkowników) jest **wyłączona**. Użytkownik
  nie wygeneruje więc sobie tokenu API.
- Strona nie ma `robots.txt` (404), ale **scrapowanie Pegaza sesją
  użytkownika odpada** — to obejście zabezpieczeń, kruche i sprzeczne
  z zasadą 1.

### Warianty

| Wariant | Co daje | Czego wymaga |
|---|---|---|
| **A. Kalendarz iCal** | terminy zadań, testów i wydarzeń kursów („co mam do oddania w tym tygodniu?”) | eksport kalendarza w Pegazie (Kalendarz → Eksportuj) — sprawdzić, czy jest dostępny; adres z tokenem wkleja osoba w Ustawieniach (przechowywany zaszyfrowany) |
| **B. Usługa mobilna** | pełne API: kursy (`core_enrol_get_users_courses`), terminy (`core_calendar_get_action_events_by_timesort`), zadania i stan oddania (`mod_assign_get_assignments`, `mod_assign_get_submission_status`), oceny (`gradereport_user_get_grade_items`), materiały (`core_course_get_contents`) | DRiJK włącza `enablemobilewebservice`; osoba bierze klucz z Pegaza (Preferencje → Klucze bezpieczeństwa) albo przez `admin/tool/mobile/launch.php` |
| **C. Osobna usługa dla czatu** | jak B, ale tylko wybrane funkcje (najmniejsze uprawnienia) | DRiJK tworzy usługę zewnętrzną z listą funkcji i pozwala użytkownikom tworzyć do niej tokeny |

### Wykonalność

- **A — wysoka**, jeśli eksport kalendarza jest włączony (do sprawdzenia na
  koncie studenta); bez udziału DRiJK.
- **B/C — zależna od DRiJK**; technicznie prosta (REST Moodle, token w
  nagłówku, wzorzec narzędzi z USOS).

### Przebieg

0. Sprawdzić eksport kalendarza na własnym koncie; wysłać zapytanie do DRiJK
   (szablon niżej) — prośba o wariant C, zapasowo B.
1. **Wariant A:** wczytanie i parsowanie iCal, narzędzie `pegaz_my_deadlines`,
   zapis adresu jak token USOS.
2. **Wariant B/C (po zgodzie):** połączenie konta (wspólne „połączone konta”
   z gałęzi 3), narzędzia: kursy, terminy, stan zadań, oceny, treść materiału
   na żądanie (z limitem rozmiaru).
3. Ewaluacja od pytania do odpowiedzi.

### Ryzyka

- Materiały kursów to utwory prowadzących — tylko dla osoby, która ma do nich
  dostęp, na jej pytanie; nigdy do wspólnego indeksu.
- Adres iCal działa jak hasło (token w adresie) — szyfrowany, nigdy w logach.

## Prace przekrojowe

- **Połączone konta** (USOS + Microsoft + Pegaz) — jedna tabela, jedno
  szyfrowanie, jeden widok w Ustawieniach, wspólne zasady zgody i rozłączania.
- **Odświeżanie źródeł** — `refresh-usos.sh` → skrypt dla dowolnego źródła,
  wpisy crona i `MAX_DATA_AGE` dla `uj_pages` i `mordor`.
- **Prompt** — nowe sekcje kontekstu (np. dane z Pegaza i Teams w sekcji
  danych osoby) wymagają akceptacji; każda integracja dopisuje narzędzia do
  sekcji „DANE UŻYTKOWNIKA”.
- **Informacja dla użytkowników** — przy każdej integracji ekran zgody (jakie
  dane, dokąd trafiają, jak cofnąć), jak przy USOS.

## Decyzje do podjęcia

| Decyzja | Kto | Gałąź |
|---|---|---|
| sposób dostępu do danych Mordoru (API / eksport), zakres folderów, grupa uprawnionych | zarząd KSI + opiekunowie Mordoru | 1 |
| OCR: na serwerze nocą, na innej maszynie czy modelem z wizją (koszt) | zarząd KSI | 1 |
| prośba o zgodę dla ii.uj.edu.pl / im.uj.edu.pl | zarząd KSI | 2 |
| wysłanie zapytań do IT UJ i DRiJK | zarząd KSI | 3, 4 |
| zakres Teams (bez streszczeń cudzych wiadomości czy z nimi, po opinii IOD) | zarząd KSI | 3 |

## Szablony zapytań

**Do IT UJ (administratorzy Microsoft 365):**

> Dzień dobry, Koło Studentów Informatyki UJ rozwija czat dla studentów
> (https://chat.ksi.sh). Chcielibyśmy, żeby student mógł po zalogowaniu
> kontem UJ poprosić czat o pomoc z materiałami swoich zespołów Teams.
> Aplikacja działałaby tylko w imieniu zalogowanej osoby i tylko do odczytu,
> z uprawnieniami: Team.ReadBasic.All, Channel.ReadBasic.All, Files.Read.All,
> EduAssignments.ReadBasic (ewentualnie ChannelMessage.Read.All). Czy tenant
> UJ dopuszcza zgodę administratora dla takiej aplikacji i jaka jest
> procedura? Chętnie przedstawimy szczegóły i zasady przetwarzania danych.

**Do DRiJK (Pegaz, `elearning@uj.edu.pl`):**

> Dzień dobry, Koło Studentów Informatyki UJ rozwija czat dla studentów
> (https://chat.ksi.sh). Chcielibyśmy, żeby student mógł zapytać czat
> o terminy i stan swoich zadań w Pegazie. Czy byłoby możliwe utworzenie
> usługi zewnętrznej Moodle z wybranymi funkcjami tylko do odczytu
> (core_enrol_get_users_courses, core_calendar_get_action_events_by_timesort,
> mod_assign_get_assignments, mod_assign_get_submission_status), do której
> użytkownik mógłby wygenerować własny token — albo włączenie usługi
> mobilnej? Token byłby przechowywany zaszyfrowany i używany tylko na
> pytanie danej osoby.

## Źródła

- Microsoft Graph — opis uprawnień i wymagań zgody:
  https://learn.microsoft.com/en-us/graph/permissions-reference
- Domyślna polityka zgód Microsoftu blokuje m.in. pliki, witryny, czaty,
  kalendarz i spotkania (2025):
  https://blog.topedia.com/2025/11/microsoft-managed-default-app-consent-policy-now-blocks-20-additional-permissions/,
  https://office365itpros.com/2025/06/19/app-consent-policy-user-app-consent/
- Publiczna konfiguracja Pegaza:
  `POST https://pegaz.uj.edu.pl/lib/ajax/service-nologin.php` z
  `tool_mobile_get_public_config`
- Tenant UJ: `https://login.microsoftonline.com/uj.edu.pl/v2.0/.well-known/openid-configuration`
- Pliki `robots.txt` serwisów wymienionych w gałęzi 2 (stan z 2026-10-27).
