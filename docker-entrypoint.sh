#!/bin/sh
# Start kontenera backendu: jako root tylko poprawia wlasciciela wolumenow
# (wolumeny sprzed uzytkownika "app" i pliki zapisane przez
# "docker compose exec" jako root), potem uruchamia polecenie jako "app" bez
# zadnych uprawnien roota - parser PDF-ow i model nie dzialaja jako root.
set -eu

if [ "$(id -u)" = 0 ]; then
  mkdir -p "$HF_HOME"
  # /app/.cache: model (HF_HOME) i inne cache bibliotek w katalogu domowym
  for dir in /app/db /app/data /app/dataset /app/uploads /app/.cache; do
    mkdir -p "$dir"
    if [ -n "$(find "$dir" ! -user app -print -quit)" ]; then
      chown -R app:app "$dir"
    fi
  done
  exec setpriv --reuid=app --regid=app --init-groups --inh-caps=-all --no-new-privs -- "$@"
fi

exec "$@"
