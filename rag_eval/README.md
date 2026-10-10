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

`LLM_PROVIDER=openrouter` odtwarza produkcję: przepisywanie dopytań działa
tylko z Ollamą, więc tu jest wyłączone.

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
