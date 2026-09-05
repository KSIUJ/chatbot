#!/bin/sh
# Buduje i uruchamia caly stos (backend + frontend, opcjonalnie Ollama) przez
# Docker Compose. Patrz docs/DOCKER.md po pelny opis, flagi i troubleshooting.
#
# Uzycie:
#   ./scripts/docker-up.sh              # backend + frontend, LLM_PROVIDER z .env (claude/cursor/openrouter)
#   ./scripts/docker-up.sh --ollama      # + lokalny model przez Ollame (profil "ollama")
#   ./scripts/docker-up.sh --ollama --gpu  # jw. + akceleracja NVIDIA (wymaga karty + Container Toolkit)
set -e

# Git Bash na Windowsie przerabia sciezki POSIX w argumentach na sciezki
# Windowsa (np. "/api/" -> "C:/Program Files/Git/api/") - bez tego bind mounty
# i sciezki w kontenerze potrafia sie wywrocic. Bez znaczenia na Linux/macOS.
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."

PROFILE_ARGS=""
FILE_ARGS="-f docker-compose.yml"

for arg in "$@"; do
    case "$arg" in
        --ollama) PROFILE_ARGS="--profile ollama" ;;
        --gpu) FILE_ARGS="$FILE_ARGS -f docker-compose.gpu.yml" ;;
        *) echo "[docker-up] Nieznana flaga: $arg (dostepne: --ollama, --gpu)"; exit 1 ;;
    esac
done

if [ ! -f .env ]; then
    echo "[docker-up] Brak .env - tworze z .env.example (uzupelnij klucze API przed uzyciem LLM_PROVIDER innego niz ollama)."
    cp .env.example .env
fi

echo "[docker-up] docker compose $FILE_ARGS $PROFILE_ARGS up -d --build"
# shellcheck disable=SC2086
docker compose $FILE_ARGS $PROFILE_ARGS up -d --build

FRONTEND_PORT_VALUE=$(grep -E '^FRONTEND_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2)
FRONTEND_PORT_VALUE=${FRONTEND_PORT_VALUE:-8080}

echo
echo "[docker-up] Gotowe:"
echo "  Frontend: http://localhost:$FRONTEND_PORT_VALUE"
echo "  Backend:  http://localhost:8000/health"
echo
echo "[docker-up] Baza RAG w nowych wolumenach jest PUSTA. Jesli masz juz"
echo "[docker-up] lokalnie data/ i dataset/ (docs/SETUP.md), zaladuj je teraz:"
echo "  ./scripts/docker-seed-data.sh"
echo "[docker-up] W przeciwnym razie patrz docs/DOCKER.md, sekcja 'Dane RAG'."
