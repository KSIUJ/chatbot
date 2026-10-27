# Ewaluacja RAG-a

Zbiór pytań z oczekiwanymi źródłami i skrypt, który mierzy wyszukiwanie: czy
właściwe źródło trafia do kontekstu modelu (i na którym miejscu), ile szumu
dostaje pytanie bez odpowiedzi, ile trwa wyszukiwanie i ile pamięci zużywa
proces. Stary i nowy RAG są mierzone tym samym zbiorem — po to, żeby
przebudowa była sprawdzalna.

- `questions.jsonl` — pytania (kategorie: `staff`, `study`, `faculty`, `usos`,
  `groups`, `ksi`, `mordor`, `followup`, `english`, `none`). Pisane ręcznie, bez
  treści od użytkowników (repo jest publiczne). `expected` to cele z
  `targets.py`; pusta lista = w danych nie ma odpowiedzi albo pytanie jest poza
  zakresem.
- `targets.py` — format celów (`page:`, `staff:`, `mordor:`, `ksi:`),
  niezależny od budowy RAG-a.
- `systems/` — systemy pod testem; `current` to obecny `src/backend/rag/`.
- `run.py` — przebieg i podsumowanie; wyniki w `results/<nazwa>.json`
  (poza gitem), punkt odniesienia w `baseline-current.json`.

## Uruchomienie

Dane (`data/`, `dataset/`) w katalogu roboczym poza repo, model embeddingów
z wolumenu `hf-cache`. Limit pamięci chroni produkcję na tym samym serwerze:

```bash
docker run --rm --memory=1700m --memory-swap=1700m --user 1000:1000 \
  -v "$PWD":/repo -v ~/rag-workdir:/work -v chatbot_hf-cache:/hf:ro \
  -e HF_HOME=/hf -e HF_HUB_OFFLINE=1 -e LLM_PROVIDER=openrouter \
  -e PYTHONPATH=/repo -e HOME=/tmp -w /work --entrypoint python \
  <obraz backendu z pytest> -m rag_eval.run --name moj-przebieg
```

`LLM_PROVIDER=openrouter` odtwarza produkcję. Bez klucza API przepisanie
dopytania przez model się nie udaje i działa regułowy zapas z
`llm/rewrite.py` (poprzednie pytanie + dopytanie) — to on jest tu mierzony.

## Punkt odniesienia (obecny RAG, dane z produkcji z 2026-10-11)

270 stron, 208 pracowników, Mordor pusty, brak źródła KSI.

| kategoria | pytań | @1 | @3 | @5 | w kontekście | MRR |
|---|---|---|---|---|---|---|
| wszystkie | 133 | 48% | 58% | 73% | 73% | 0,557 |
| bez `ksi`/`mordor` (są dane) | 111 | 54% | — | — | 81% | — |
| staff | 30 | 97% | 97% | 97% | 97% | 0,967 |
| usos | 14 | 71% | 86% | 100% | 100% | 0,81 |
| faculty | 15 | 40% | 47% | 80% | 80% | 0,502 |
| study | 28 | 39% | 54% | 75% | 75% | 0,502 |
| groups | 8 | 12% | 62% | 62% | 62% | 0,354 |
| english | 6 | 33% | 33% | 100% | 100% | 0,5 |
| followup | 10 | 10% | 10% | 30% | 30% | 0,15 |
| ksi | 8 | 0% | 12% | 12% | 12% | 0,042 |
| mordor | 6 | 0% | 0% | 0% | 0% | 0 |

Pytania bez odpowiedzi dostają zawsze 5 trafień (brak progu trafności).
Wyszukiwanie: p50 1,13 s, p95 1,39 s; pamięć procesu 1,7 GB; start 36 s
(procesor VM bez AVX2).

## Narzędzia USOS (od pytania do odpowiedzi)

`usos_tools.py` z `usos_tools.jsonl` sprawdza całą ścieżkę z danymi osoby:
prawdziwy model z produkcji (`LLM_PROVIDER` z `.env`), RAG i narzędzia USOS
(`src/backend/usos/tools.py`) dla konta, które połączyło USOS. Dla każdego
pytania: czy model wywołał oczekiwane narzędzia (albo żadnego, gdy pytanie nie
dotyczy własnych danych), czy narzędzia nie zwróciły błędu, czy odpowiedź
korzysta z ich wyniku, czy godziny i numery sal z odpowiedzi są w danych
narzędzi albo w kontekście RAG, czy nie ma zwrotów typu „USOS nie odpowiada”,
surowego JSON-a ani tokenu, a próba obejścia zasad zaczyna się od
`[[NARUSZENIE]]`. Dopytania (`history`) idą z prawdziwymi wcześniejszymi
odpowiedziami modelu.

Odpowiedzi zawierają dane osoby, więc nie są zapisywane — `results/<nazwa>.json`
ma tylko flagi, nazwy narzędzi, liczby i niepotwierdzone godziny/sale
(`--show-answers` wypisuje odpowiedzi na ekran, tylko dla własnego konta).
Kopia bazy z połączonym kontem w `/db`, kopia indeksu i danych w `/work`:

```bash
docker run --rm --memory=2500m --user 1000:1000 -v "$PWD":/repo -v <kopia>:/work \
  -v <katalog z chatbot.db>:/db -v chatbot_hf-cache:/hf:ro -e HF_HOME=/hf -e HF_HUB_OFFLINE=1 \
  -e PYTHONPATH=/repo -e HOME=/tmp -w /work --entrypoint python chatbot-scrapers \
  -m rag_eval.usos_tools --name usos-1 --username <login>
```

Przebieg z 2026-10-27 (Claude Haiku 5.5, 39 pytań): 39/39 — narzędzia 35/35,
błędy 0, oparte na danych 29/29, godziny i sale 29/29, odmowa przy próbie
obejścia ze znacznikiem; średnio 5 s na pytanie.
