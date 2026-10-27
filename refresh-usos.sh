#!/usr/bin/env bash
# Odswiezenie danych USOS na dzialajacym czacie: scraper (pipeline/scrapers/usos)
# zapisuje zbior prosto do wolumenu danych backendu, a potem sync indeksu RAG
# podmienia tylko zmienione dokumenty. Do crona (np. co noc), ale mozna recznie.
#
#   ./refresh-usos.sh                bez kart pracownikow (zostaja z poprzedniego zbioru)
#   ./refresh-usos.sh --with-staff   tez pracownicy, z tokenem operatora z .env (adresy e-mail)
#
# Bez --with-staff scraper dziala samym kluczem aplikacji: token operatora
# (USOS_ACCESS_TOKEN) bywa niewazny, a bez niego karty pracownikow stracilyby
# adresy e-mail - dlatego pracownicy zostaja wtedy z poprzedniego zbioru.
#
# Wszystko jako uzytkownik app kontenera backendu (uid 10001): pliki indeksu
# zapisane przez roota backend widzi tylko do odczytu i przestaje odpowiadac.
set -euo pipefail
umask 022

cd "$(dirname "$0")"

APP_UID=10001
APP_GID=999
IMAGE=chatbot-scrapers
DATA_VOLUME=chatbot_chatbot-data
# wszystkie kolektory poza staff (staff i tak dziala jako zaleznosc courses)
WITHOUT_STAFF=calendar,units,courses,programmes,registrations,news,places,pages
LOG_DIR=logs
LOG="$LOG_DIR/refresh-usos.log"

with_staff=false
case "${1:-}" in
  "") ;;
  --with-staff) with_staff=true ;;
  -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "nieznana opcja: $1 (--help)" >&2; exit 2 ;;
esac

mkdir -p "$LOG_DIR"
exec >>"$LOG" 2>&1
echo "==> $(date -Is) odswiezanie USOS (pracownicy: $with_staff)"

# jedno odswiezanie naraz (cron + reczne)
exec 9>"$LOG_DIR/refresh-usos.lock"
if ! flock -n 9; then
  echo "inne odswiezanie trwa - koncze"
  exit 0
fi

# obraz backendu z ostatniego deployu + biblioteki scraperow (z cache - zwykle od razu)
if ! docker build -q -f Dockerfile.scrapers -t "$IMAGE" . >/dev/null; then
  echo "nie udalo sie zbudowac obrazu $IMAGE"
  exit 1
fi

# klucz aplikacji (i przy --with-staff token operatora) z .env - tylko te zmienne
if $with_staff; then
  keys='^USOS_(CONSUMER_KEY|CONSUMER_SECRET|ACCESS_TOKEN|ACCESS_TOKEN_SECRET)='
  only=()
  no_token=()
else
  keys='^USOS_(CONSUMER_KEY|CONSUMER_SECRET)='
  only=(--only "$WITHOUT_STAFF")
  # -e wygrywa z --env-file: bez tokenu, nawet gdyby byl w srodowisku
  no_token=(-e USOS_ACCESS_TOKEN= -e USOS_ACCESS_TOKEN_SECRET=)
fi

# .env repozytorium ma prawa 600 - w kontenerze jest zasloniety (zmienne ida przez --env-file)
if ! docker run --rm --user "$APP_UID:$APP_GID" \
    -v "$PWD:/app:ro" -v /dev/null:/app/.env:ro -v "$DATA_VOLUME:/data" -w /app \
    -e HOME=/tmp -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
    "${no_token[@]}" --env-file <(grep -E "$keys" .env) \
    "$IMAGE" python -m pipeline.scrapers.usos scrape "${only[@]}" --out /data/usos; then
  echo "scraper nie zapisal zbioru - indeks bez zmian"
  exit 1
fi

docker compose exec -T -u app backend python -m src.backend.rag.index sync --source usos
echo "==> $(date -Is) gotowe"
