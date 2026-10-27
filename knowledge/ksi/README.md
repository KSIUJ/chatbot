# Informacje o KSI dla czatu

Notatki w tym katalogu trafiają do bazy wiedzy czatu (źródło `ksi`, obok stron
KSI). Pisz je dla studenta, który pyta czat o koło: krótko, konkretnie,
z aktualnymi danymi. **Repozytorium jest publiczne** — tylko informacje,
które mogą być publiczne (bez haseł, danych prywatnych, terminów konkursu
odznak).

Jedna notatka = jeden plik `nazwa-tematu.md`. Plik zaczyna się nagłówkiem:

```markdown
---
title: Jak dołączyć do KSI
updated: 2026-10-01
tags: [członkostwo]
url: https://ksi.ii.uj.edu.pl/   # opcjonalnie: strona z pełną informacją
always_include: false            # opcjonalnie: dołączać zawsze przy pytaniach o KSI
draft: true                      # opcjonalnie: szkic, nie trafia do czatu
---

Treść w Markdownie: akapity, listy, nagłówki `##`.
```

- `title` jest wymagany; `updated` to data ostatniego sprawdzenia treści.
- Pliki zaczynające się od `_` (np. `_szablon.md`) i ten README są pomijane.
- Sprawdzenie formatu: `python -m src.backend.rag.datasets_cli check --source ksi`.
- Po zmianie notatek trzeba przebudować indeks (`python -m src.backend.rag.index sync --source ksi`).

## Poradniki USOS (`usos-*.md`)

Krótkie poradniki do USOSweb (rejestracje, plan, podpięcia, APD, wnioski...)
zamiast stron USOSowni UJ, której `robots.txt` zabrania robotów — dlatego nie
jest pobierana scraperem. Piszemy własnymi słowami tylko ogólne, stałe fakty
(bez cen, terminów i procedur jednego wydziału), a `url` prowadzi do pełnej
instrukcji w USOSowni. Fakty sprawdzamy na stronach, które wolno pobierać
(USOSweb, strony wydziału).
