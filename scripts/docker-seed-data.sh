#!/bin/sh
# Kopiuje istniejace lokalne data/ i dataset/ (scrapy + baza wektorowa RAG)
# do wolumenow Dockera (chatbot-data, chatbot-dataset). Bez tego backend w
# kontenerze startuje z pusta baza RAG - odpowiada, ale nic nie wie o
# wydziale, bo wolumeny sa puste przy pierwszym "docker compose up".
#
# Zalozenie: masz juz lokalnie zescrapowane/zingestowane dane (patrz
# docs/SETUP.md, sekcje 6-7) - ten skrypt tylko je przenosi do Dockera,
# NIE scrapuje ani nie ingestuje niczego sam.
#
# Uzycie (z katalogu glownego repo, stos musi byc juz zbudowany):
#   ./scripts/docker-seed-data.sh
set -e

# Git Bash na Windowsie przerabia sciezki POSIX w argumentach na sciezki
# Windowsa - bez tego bind mounty ponizej potrafia sie wywrocic. Bez
# znaczenia na Linux/macOS.
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."

if [ ! -d data ] && [ ! -d dataset ]; then
    echo "[seed] Brak lokalnych data/ i dataset/ - nie ma czego kopiowac."
    echo "[seed] Zescrapuj i zingestuj dane lokalnie (docs/SETUP.md, sekcje 6-7)"
    echo "[seed] albo uruchom ingest bezposrednio w kontenerze - patrz docs/DOCKER.md."
    exit 1
fi

echo "[seed] Kopiuje data/ i dataset/ do wolumenow Dockera (uslugu 'backend', bez zaleznosci)..."
docker compose run --rm --no-deps --entrypoint sh \
    -v "$(pwd)/data:/host-data:ro" \
    -v "$(pwd)/dataset:/host-dataset:ro" \
    backend -c '
        [ -d /host-data ] && cp -a /host-data/. /app/data/ && echo "  data/    -> OK"
        [ -d /host-dataset ] && cp -a /host-dataset/. /app/dataset/ && echo "  dataset/ -> OK"
    '

echo "[seed] Gotowe. Restartuje backend, zeby na pewno zaladowal swieze dane..."
docker compose restart backend

echo "[seed] Sprawdz liczby w bazie:"
echo "  docker compose exec backend python -c \"from src.backend.RAG.vectorstore import VectorStore; c=VectorStore().collection; print({s: len(c.get(where={'source': s})['ids']) for s in ['mordor','strony','usos']}, 'total', c.count())\""
