#!/usr/bin/env bash
# Uruchomienie calego czatu jednym poleceniem (backend + frontend, przy
# LLM_PROVIDER=ollama takze Ollama): sprawdza Dockera i .env, robi kopie bazy
# kont i rozmow, buduje obrazy, startuje kontenery i czeka, az strona odpowie.
#
#   ./deploy.sh            start albo aktualizacja po zmianach w kodzie
#   ./deploy.sh --pull     najpierw git pull (wdrozenie na serwerze)
#   ./deploy.sh --help     wszystkie opcje
set -euo pipefail
# kopie bazy (konta, rozmowy) i nowy .env tylko dla wlasciciela
umask 077

cd "$(dirname "$0")"
# Git Bash na Windows przerabia argumenty zaczynajace sie od "/" na sciezki Windows
export MSYS_NO_PATHCONV=1

MIN_SECRET_KEY_LENGTH=32   # jak w src/backend/auth/settings.py
BACKUPS_DIR=backups
BACKUPS_KEPT=10
# starszych kopii nie trzymamy (jak CHAT_HISTORY_RETENTION_DAYS) - zawieraja
# rozmowy, ktore z bazy juz znikly
BACKUPS_MAX_AGE_DAYS=30

usage() {
  cat <<'EOF'
Uzycie: ./deploy.sh [opcje]

  --pull         przed startem git pull --ff-only (wymaga czystego drzewa)
  --seed         skopiuj lokalne data/ i dataset/ (dane RAG) do kontenera
  --ollama       wymus lokalna Ollame (domyslnie: gdy LLM_PROVIDER=ollama)
  --no-ollama    bez Ollamy, nawet przy LLM_PROVIDER=ollama
  --gpu          Ollama na GPU NVIDIA (docker-compose.gpu.yml, wlacza --ollama)
  --no-backup    bez kopii bazy przed startem
  --timeout S    ile sekund czekac, az strona odpowie (domyslnie 600)
  -h, --help     ta pomoc

Zatrzymanie: docker compose down   Logi: docker compose logs -f backend
EOF
}

if [ -t 1 ]; then BLUE=$'\033[1;34m'; YELLOW=$'\033[1;33m'; RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; RESET=$'\033[0m'
else BLUE=''; YELLOW=''; RED=''; GREEN=''; RESET=''; fi
log()  { printf '%s==>%s %s\n' "$BLUE" "$RESET" "$*"; }
warn() { printf '%s!!%s  %s\n' "$YELLOW" "$RESET" "$*" >&2; }
die()  { printf '%sBLAD:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

# --- opcje ---------------------------------------------------------------

PULL=0; SEED=0; OLLAMA=auto; GPU=0; BACKUP=1; TIMEOUT=600
ARGS_WITHOUT_PULL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --pull) PULL=1 ;;
    --seed) SEED=1 ;;
    --ollama) OLLAMA=1 ;;
    --no-ollama) OLLAMA=0 ;;
    --gpu) GPU=1; OLLAMA=1 ;;
    --no-backup) BACKUP=0 ;;
    --timeout)
      [ $# -ge 2 ] && [[ $2 =~ ^[0-9]+$ ]] || die "--timeout wymaga liczby sekund"
      TIMEOUT=$2; ARGS_WITHOUT_PULL+=("$1"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "nieznana opcja: $1" ;;
  esac
  [ "$1" = --pull ] || ARGS_WITHOUT_PULL+=("$1")
  shift
done

# --- narzedzia -----------------------------------------------------------

command -v docker >/dev/null 2>&1 || die "brak Dockera (https://docs.docker.com/engine/install/)"
docker compose version >/dev/null 2>&1 || die "potrzebny Docker Compose v2 (polecenie 'docker compose')"
docker info >/dev/null 2>&1 || die "Docker nie dziala - uruchom Docker Desktop albo usluge docker"
command -v curl >/dev/null 2>&1 || die "brak curl (potrzebny do sprawdzenia, czy strona odpowiada)"

# --- aktualizacja kodu ---------------------------------------------------

if [ "$PULL" = 1 ]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "niezatwierdzone zmiany w repo - --pull ich nie nadpisze"
  fi
  log "git pull --ff-only"
  git pull --ff-only
  # skrypt mogl sie zmienic: dalej dziala juz nowa wersja
  exec "./$(basename "$0")" "${ARGS_WITHOUT_PULL[@]+"${ARGS_WITHOUT_PULL[@]}"}"
fi

# --- konfiguracja (.env) -------------------------------------------------

if [ ! -f .env ]; then
  cp .env.example .env
  die "utworzono .env z .env.example - uzupelnij OIDC_CLIENT_SECRET, AUTH_SECRET_KEY i klucz LLM, potem uruchom ponownie.
  Klucz sesji: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
fi

# Wartosc KEY z .env bez wykonywania pliku (.env to dane, nie skrypt): ostatnie
# wystapienie, bez CR, spacji, cudzyslowow i komentarza po wartosci bez cudzyslowu.
env_value() {
  local line value
  line=$(grep -E "^[[:space:]]*(export[[:space:]]+)?$1[[:space:]]*=" .env | tail -n 1 || true)
  value=${line#*=}
  value=${value%$'\r'}
  value="${value#"${value%%[![:space:]]*}"}"
  case $value in
    \"*\") value=${value#\"}; value=${value%\"} ;;
    \'*\') value=${value#\'}; value=${value%\'} ;;
    *) value=${value%%[[:space:]]#*} ;;
  esac
  printf '%s' "${value%"${value##*[![:space:]]}"}"
}

missing=()
for key in OIDC_ISSUER OIDC_CLIENT_ID OIDC_CLIENT_SECRET OIDC_REDIRECT_URI AUTH_SECRET_KEY; do
  [ -n "$(env_value "$key")" ] || missing+=("$key")
done
[ ${#missing[@]} -eq 0 ] || die "w .env brakuje: ${missing[*]} (opis w .env.example)"
secret=$(env_value AUTH_SECRET_KEY)
[ ${#secret} -ge $MIN_SECRET_KEY_LENGTH ] || die "AUTH_SECRET_KEY musi miec co najmniej $MIN_SECRET_KEY_LENGTH znaki"
unset secret

provider=$(env_value LLM_PROVIDER | tr '[:upper:]' '[:lower:]')
provider=${provider:-ollama}
case $provider in
  ollama) ;;
  claude) [ -n "$(env_value ANTHROPIC_API_KEY)" ] || die "LLM_PROVIDER=claude wymaga ANTHROPIC_API_KEY" ;;
  openrouter) [ -n "$(env_value OPENROUTER_API_KEY)" ] || die "LLM_PROVIDER=openrouter wymaga OPENROUTER_API_KEY" ;;
  cursor) [ -n "$(env_value CURSOR_API_KEY)" ] || die "LLM_PROVIDER=cursor wymaga CURSOR_API_KEY" ;;
  *) die "nieznany LLM_PROVIDER=$provider (ollama, claude, openrouter, cursor)" ;;
esac
[ "$OLLAMA" = auto ] && { [ "$provider" = ollama ] && OLLAMA=1 || OLLAMA=0; }

port=$(env_value FRONTEND_PORT)
port=${port:-8080}
[[ $port =~ ^[0-9]+$ ]] || die "FRONTEND_PORT musi byc numerem portu"
URL="http://127.0.0.1:$port"

COMPOSE=(docker compose -f docker-compose.yml)
[ "$GPU" = 1 ] && COMPOSE+=(-f docker-compose.gpu.yml)
[ "$OLLAMA" = 1 ] && COMPOSE+=(--profile ollama)

# --- kopia bazy ----------------------------------------------------------

# Spojna kopia SQLite (backup API, takze przy dzialajacym backendzie) wypisana
# na stdout; kod 3 = bazy jeszcze nie ma.
BACKUP_PY='import os, sqlite3, sys
src = "/app/db/chatbot.db"
if not os.path.exists(src):
    sys.exit(3)
tmp = "/tmp/deploy-backup.db"
source, target = sqlite3.connect(src), sqlite3.connect(tmp)
source.backup(target)
target.close(); source.close()
with open(tmp, "rb") as f:
    sys.stdout.buffer.write(f.read())
os.remove(tmp)'

backup_database() {
  local runner file status=0
  if [ -n "$("${COMPOSE[@]}" ps -q --status running backend 2>/dev/null)" ]; then
    runner=("${COMPOSE[@]}" exec -T backend)
  elif docker image inspect "$("${COMPOSE[@]}" config --images backend 2>/dev/null | head -n 1)" >/dev/null 2>&1; then
    runner=("${COMPOSE[@]}" run --rm --no-deps -T backend)
  else
    log "pierwsze uruchomienie - nie ma jeszcze bazy do skopiowania"
    return
  fi
  mkdir -p "$BACKUPS_DIR"
  # kopie sprzed umask 077 tez tylko dla wlasciciela
  chmod 700 "$BACKUPS_DIR"
  chmod 600 "$BACKUPS_DIR"/chatbot-*.db 2>/dev/null || true
  file="$BACKUPS_DIR/chatbot-$(date +%Y%m%d-%H%M%S).db"
  "${runner[@]}" python -c "$BACKUP_PY" > "$file" || status=$?
  if [ "$status" = 3 ]; then
    rm -f "$file"; log "baza jeszcze nie istnieje - bez kopii"; return
  fi
  if [ "$status" != 0 ] || [ "$(head -c 15 "$file" 2>/dev/null)" != "SQLite format 3" ]; then
    rm -f "$file"; die "kopia bazy nie powiodla sie (bez kopii: --no-backup)"
  fi
  log "kopia bazy: $file"
  # tylko ostatnie kopie, zeby nie zapelnic dysku (nazwy sa nasze, bez spacji)
  # shellcheck disable=SC2012
  ls -1t "$BACKUPS_DIR"/chatbot-*.db 2>/dev/null | tail -n +$((BACKUPS_KEPT + 1)) | xargs -r rm -f --
  # i nie starsze niz BACKUPS_MAX_AGE_DAYS (swieza kopia przed chwila powstala)
  find "$BACKUPS_DIR" -maxdepth 1 -name 'chatbot-*.db' -mtime +"$BACKUPS_MAX_AGE_DAYS" -delete
}

[ "$BACKUP" = 1 ] && backup_database

# --- start ---------------------------------------------------------------

diagnostics() {
  warn "stan kontenerow:"
  "${COMPOSE[@]}" ps -a >&2 || true
  warn "ostatnie logi backendu:"
  "${COMPOSE[@]}" logs --tail 40 backend >&2 || true
}

wait_for_site() {
  local deadline=$((SECONDS + TIMEOUT))
  log "czekam, az $URL odpowie (do ${TIMEOUT} s)"
  # wynik przez przekierowanie powloki, nie "curl -o /dev/null": z
  # MSYS_NO_PATHCONV curl.exe na Windows nie zna sciezki /dev/null
  until curl -fsS --max-time 5 "$URL/api/health" >/dev/null 2>&1; do
    if [ $SECONDS -ge $deadline ]; then
      diagnostics; die "strona nie odpowiada po ${TIMEOUT} s"
    fi
    sleep 3
  done
  curl -fsS --max-time 5 "$URL/" >/dev/null || { diagnostics; die "frontend nie odpowiada pod $URL"; }
}

log "budowanie obrazow i start (LLM: $provider$([ "$OLLAMA" = 1 ] && echo ", Ollama$([ "$GPU" = 1 ] && echo " na GPU")"))"
"${COMPOSE[@]}" up -d --build --remove-orphans || { diagnostics; die "docker compose up nie powiodl sie"; }
wait_for_site

# --- dane RAG ------------------------------------------------------------

if [ "$SEED" = 1 ]; then
  for dir in data dataset; do
    if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
      log "kopiuje $dir/ do kontenera"
      "${COMPOSE[@]}" cp "$dir/." "backend:/app/$dir"
    else
      warn "brak lokalnego $dir/ - pomijam"
    fi
  done
  "${COMPOSE[@]}" restart backend
  wait_for_site
fi

# shellcheck disable=SC2016  # $(...) ma sie wykonac w kontenerze, nie tutaj
if ! "${COMPOSE[@]}" exec -T backend sh -c '[ -n "$(ls -A /app/dataset 2>/dev/null)" ]'; then
  warn "baza RAG jest pusta - bot nie zna danych wydzialu. Skopiuj je: ./deploy.sh --seed"
  warn "albo zbuduj indeks: docker compose exec -u app backend python -m src.backend.rag.index build"
  warn "(pozniej aktualizacja: ... index sync, stan: ... index status, powrot: ... index rollback)"
fi
[ "$OLLAMA" = 1 ] && log "model Ollamy pobiera sie w tle przy pierwszym starcie: docker compose logs -f ollama-pull"

"${COMPOSE[@]}" ps
printf '\n%sGotowe:%s %s   (logi: docker compose logs -f backend, stop: docker compose down)\n' "$GREEN" "$RESET" "$URL"
