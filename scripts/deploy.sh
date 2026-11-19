#!/usr/bin/env bash
# Wdraża czat na serwerze: kopiuje kod przez rsync, robi kopię bazy, buduje
# nowe obrazy obok działających kontenerów, podmienia je i dopiero na końcu
# sprząta stare obrazy. Przerwa w działaniu to sam restart kontenerów (kilka
# sekund), a nie czas budowania.
#
# Nieudany start cofa wdrożenie: kontenery wracają na poprzednie obrazy, które
# do tego momentu leżą nietknięte na dysku. Uwaga: migracje bazy nowej wersji
# zostają - przy cofnięciu po migracji przywróć kopię z $DEST/backups/.
#
#   scripts/deploy.sh              # z pytaniem o potwierdzenie
#   scripts/deploy.sh -y           # bez pytania
#   scripts/deploy.sh --dry-run    # pokaż, co zostałoby skopiowane
#
# Zmienne: KSI_HOST (alias SSH), KSI_DEST, KSI_PROJECT
#
# ./deploy.sh w katalogu głównym to uruchomienie całości lokalnie w Dockerze.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${KSI_HOST:-ksi-chat}"
DEST="${KSI_DEST:-/opt/chatbot}"
# Nazwa projektu Compose = prefiks wolumenów (chatbot_chatbot-db, ...) i obrazów
# (chatbot-backend, chatbot-frontend); refresh-usos.sh zakłada tę samą.
PROJECT="${KSI_PROJECT:-chatbot}"
ASSUME_YES=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    -y|--yes)     ASSUME_YES=1 ;;
    -n|--dry-run) DRY_RUN=1 ;;
    -h|--help)    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Nieznany argument: $arg" >&2; exit 2 ;;
  esac
done

# Konfiguracja, dane i kopie żyją wyłącznie na serwerze i nigdy nie jadą
# z repo. Są też wykluczone z --delete: rsync nie kasuje po stronie odbiorcy
# tego, czego nie widzi po stronie nadawcy.
EXCLUDES=(
  # pierwsza pasująca reguła wygrywa: .env.example jedzie, inne .env.* nie
  --include=.env.example
  --exclude=.git
  --exclude=.env
  "--exclude=.env.*"
  --exclude=/REVISION
  --exclude=/data/
  --exclude=/dataset/
  --exclude=/backups/
  --exclude=/uploads/
  --exclude=/logs/
  "--exclude=*.db"
  "--exclude=*.db.bak*"
  --exclude=.venv/
  --exclude=__pycache__/
  --exclude=.pytest_cache/
  --exclude=.ruff_cache/
  --exclude=node_modules/
  --exclude=dist/
  --exclude=coverage/
  "--exclude=*.tsbuildinfo"
  --exclude=.eslintcache
  --exclude=rag_eval/results/
  --exclude=.vscode/
  --exclude=.idea/
  --exclude=.claude/
  "--exclude=*.log"
  --exclude=.DS_Store
)

commit="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"
branch="$(git branch --show-current 2>/dev/null || echo '?')"
echo "Cel:    $HOST:$DEST (projekt Compose: $PROJECT)"
echo "Kod:    $branch @ $commit"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  echo "UWAGA:  niezacommitowane zmiany - pojadą na serwer razem z resztą" >&2
fi
echo "Zostaje nietknięte: .env, data/, dataset/, backups/, uploads/, logs/ i wolumeny Dockera"

if [[ $DRY_RUN -eq 1 ]]; then
  echo
  echo "--- rsync --dry-run ---"
  rsync -az --delete --dry-run --itemize-changes "${EXCLUDES[@]}" ./ "$HOST:$DEST/"
  exit 0
fi

# Wdrożenie bez konfiguracji na serwerze podniosłoby backend, który wysypie
# się na starcie - lepiej dowiedzieć się o tym teraz (jak ./deploy.sh).
echo
echo "Sprawdzam konfigurację na hoście…"
ssh "$HOST" bash -s -- "$DEST" <<'PREFLIGHT'
set -euo pipefail
DEST="$1"
[[ -f "$DEST/.env" ]] || { echo "BRAK: $DEST/.env (wzór: .env.example)" >&2; exit 1; }
command -v docker >/dev/null && docker compose version >/dev/null \
  || { echo "BRAK: docker z compose v2 na hoście" >&2; exit 1; }

env_value() { sed -n "s/^$1=//p" "$DEST/.env" | tail -1 | sed 's/^["'\'']//; s/["'\'']$//'; }

missing=0
mode="$(env_value ENV | tr '[:upper:]' '[:lower:]')"
[[ "$mode" == dev ]] && { echo "BŁĄD: ENV=dev na serwerze (logowanie zmyślonymi kontami, bez Keycloaka) - ustaw ENV=prod" >&2; missing=1; }
for var in OIDC_ISSUER OIDC_CLIENT_ID OIDC_CLIENT_SECRET OIDC_REDIRECT_URI AUTH_SECRET_KEY; do
  [[ -n "$(env_value "$var")" ]] || { echo "BRAK: $var w $DEST/.env" >&2; missing=1; }
done
secret="$(env_value AUTH_SECRET_KEY)"
(( ${#secret} >= 32 )) || { echo "BŁĄD: AUTH_SECRET_KEY ma mniej niż 32 znaki" >&2; missing=1; }
unset secret
[[ "$(env_value OIDC_REDIRECT_URI)" == https://* ]] \
  || { echo "BŁĄD: OIDC_REDIRECT_URI nie jest https - to konfiguracja lokalna, nie produkcyjna" >&2; missing=1; }

provider="$(env_value LLM_PROVIDER | tr '[:upper:]' '[:lower:]')"
case "${provider:-ollama}" in
  ollama) ;;
  claude)     [[ -n "$(env_value ANTHROPIC_API_KEY)" ]]  || { echo "BRAK: ANTHROPIC_API_KEY (LLM_PROVIDER=claude)" >&2; missing=1; } ;;
  openrouter) [[ -n "$(env_value OPENROUTER_API_KEY)" ]] || { echo "BRAK: OPENROUTER_API_KEY (LLM_PROVIDER=openrouter)" >&2; missing=1; } ;;
  cursor)     [[ -n "$(env_value CURSOR_API_KEY)" ]]     || { echo "BRAK: CURSOR_API_KEY (LLM_PROVIDER=cursor)" >&2; missing=1; } ;;
  *) echo "BŁĄD: nieznany LLM_PROVIDER=$provider" >&2; missing=1 ;;
esac

[[ $missing -eq 0 ]] || { echo "Popraw powyższe i uruchom ponownie." >&2; exit 1; }
echo "  .env kompletny (LLM: ${provider:-ollama})"
PREFLIGHT

if [[ $ASSUME_YES -eq 0 ]]; then
  echo
  read -r -p "Kontynuować? [t/N] " ans
  [[ "$ans" == "t" || "$ans" == "T" ]] || { echo "Przerwano."; exit 1; }
fi

echo
echo "Kopiuję kod…"
rsync -az --delete --stats "${EXCLUDES[@]}" ./ "$HOST:$DEST/" | tail -12
# Serwer nie ma repo - zapisujemy, która wersja na nim stoi.
printf '%s %s %s\n' "$commit" "$branch" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | ssh "$HOST" "cat > '$DEST/REVISION'"

echo
echo "Kopia bazy, budowanie nowych obrazów (stare kontenery działają dalej)…"
# Skrypt jedzie przez stdin (bash -s), a polecenia w nim też mogą czytać stdin
# (docker compose exec przekazuje go do kontenera) i zjadłyby resztę skryptu -
# bash skończyłby wtedy po cichu z kodem 0. Klamry każą bashowi wczytać całość
# przed uruchomieniem czegokolwiek.
ssh "$HOST" bash -s -- "$DEST" "$PROJECT" <<'REMOTE'
{
set -euo pipefail
DEST="$1"; PROJECT="$2"
cd "$DEST"
umask 077

env_value() { sed -n "s/^$1=//p" .env | tail -1 | sed 's/^["'\'']//; s/["'\'']$//'; }
PORT="$(env_value FRONTEND_PORT)"; PORT="${PORT:-8080}"
COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.yml)
provider="$(env_value LLM_PROVIDER | tr '[:upper:]' '[:lower:]')"
[[ "${provider:-ollama}" == ollama ]] && COMPOSE+=(--profile ollama)
SERVICES=(backend frontend)

# --- kopia bazy (spójna, przez backup API SQLite w działającym backendzie) ---
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
if [[ -n "$("${COMPOSE[@]}" ps -q --status running backend 2>/dev/null)" ]]; then
  mkdir -p backups && chmod 700 backups
  file="backups/chatbot-$(date +%Y%m%d-%H%M%S).db"
  status=0
  "${COMPOSE[@]}" exec -T backend python -c "$BACKUP_PY" < /dev/null > "$file" || status=$?
  if [[ $status -eq 3 ]]; then
    rm -f "$file"; echo "  baza jeszcze nie istnieje - bez kopii"
  elif [[ $status -ne 0 || "$(head -c 15 "$file")" != "SQLite format 3" ]]; then
    rm -f "$file"; echo "Kopia bazy nie powiodła się - przerywam, nic nie zostało podmienione." >&2; exit 1
  else
    echo "  kopia bazy: $DEST/$file"
    # ostatnie 10, nie starsze niż 30 dni (jak ./deploy.sh)
    ls -1t backups/chatbot-*.db | tail -n +11 | xargs -r rm -f --
    find backups -maxdepth 1 -name 'chatbot-*.db' -mtime +30 -delete
  fi
else
  echo "  backend nie działa - bez kopii bazy"
fi

# Obrazy, na których stoją kontenery - zapamiętane przed budowaniem, bo za
# chwilę tagi wskażą już nowe obrazy. To jedyna droga powrotu.
declare -A PREVIOUS IMAGE
for s in "${SERVICES[@]}"; do
  IMAGE[$s]="$("${COMPOSE[@]}" config --images "$s" | head -1)"
  cid="$("${COMPOSE[@]}" ps -q "$s" 2>/dev/null || true)"
  PREVIOUS[$s]="$([[ -n "$cid" ]] && docker inspect -f '{{.Image}}' "$cid" 2>/dev/null || true)"
done

# Budowanie nie dotyka działających kontenerów: przerwa zaczyna się dopiero
# przy `up -d`, które podmienia je na gotowe obrazy.
"${COMPOSE[@]}" build

echo "Podmieniam kontenery…"
"${COMPOSE[@]}" up -d --remove-orphans

# Sprawdzenie na miejscu: tylko tutaj da się wycofać zmianę, zanim ktokolwiek
# zobaczy niedziałającą stronę. /api/health przechodzi przez nginx frontendu
# do backendu (po migracjach), / to sam frontend.
ok=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 \
     && curl -fsS --max-time 3 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 3
done

if [[ $ok -eq 1 ]]; then
  echo "  http://127.0.0.1:$PORT/api/health -> ok"
  # Sprzątanie dopiero teraz: dopóki nowe kontenery nie odpowiedzą, stare
  # obrazy są jedyną drogą powrotu.
  docker image prune -f >/dev/null || true
  "${COMPOSE[@]}" ps --format '  {{.Name}}  {{.Status}}'
  echo "  wersja: $(cat REVISION 2>/dev/null)"
  exit 0
fi

echo "Nowe kontenery nie odpowiadają po 3 minutach." >&2
"${COMPOSE[@]}" logs --tail 40 backend >&2 || true
rolled=0
for s in "${SERVICES[@]}"; do
  if [[ -n "${PREVIOUS[$s]}" ]]; then
    docker tag "${PREVIOUS[$s]}" "${IMAGE[$s]}"; rolled=1
  fi
done
if [[ $rolled -eq 1 ]]; then
  echo "Wracam na poprzednie obrazy…" >&2
  "${COMPOSE[@]}" up -d --force-recreate --no-build
  "${COMPOSE[@]}" ps --format '  {{.Name}}  {{.Status}}' >&2
  echo "Wdrożenie wycofane - działa poprzednia wersja (kod w $DEST jest już nowy)." >&2
  echo "Jeśli nowa wersja zdążyła zmigrować bazę, a stara przez to nie działa: przywróć najnowszą kopię z $DEST/backups/." >&2
else
  echo "Nie ma na co wracać (pierwsze wdrożenie) - kontenery zostają jak są." >&2
fi
echo "Logi: cd $DEST && docker compose logs --tail=100 backend" >&2
exit 1
}
REMOTE

echo
echo "Gotowe."
