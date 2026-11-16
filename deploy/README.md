# deploy/

Wszystko, co uruchamia czat w Dockerze i na serwerze. Skrypty można wołać
z dowolnego katalogu: same przechodzą do katalogu głównego repo, a obrazy
budują się z niego jako kontekstu. Opis wdrożenia jest w głównym `README.md`.

| Plik | Do czego |
|---|---|
| `local-up.sh` | cały stack lokalnie w Dockerze (backend, frontend, opcjonalnie Ollama), `--help` |
| `deploy-server.sh` | wdrożenie z laptopa na serwer KSI (`rsync` do `/opt/chatbot`, kopia bazy, podmiana kontenerów), `--dry-run` |
| `refresh-usos.sh` | odświeżenie danych USOS na serwerze, wołane z crona: `/opt/chatbot/deploy/refresh-usos.sh` |
| `Dockerfile` | obraz backendu (zależności z grupy `app` w `pyproject.toml`) |
| `Dockerfile.scrapers` | obraz scraperów dla `refresh-usos.sh` (obraz backendu + grupa `dev`) |
| `docker-entrypoint.sh` | start kontenera backendu: właściciel wolumenów, potem użytkownik `app` |
| `compose.gpu.yml` | Ollama na GPU: `docker compose -f docker-compose.yml -f deploy/compose.gpu.yml --profile ollama up -d` |
| `constraints.txt` | `pip freeze` obrazu backendu: przypina zależności pośrednie |

`docker-compose.yml` zostaje w katalogu głównym: Compose bierze nazwę projektu
(`chatbot`) z katalogu pliku, a od niej zależą nazwy wolumenów z danymi
produkcji (`chatbot_chatbot-db` itd.).

Zmiana nazwy albo położenia skryptu wołanego na serwerze (np. `refresh-usos.sh`
z crona) wymaga zmiany na serwerze - opisz ją w PR w sekcji dla serwera.
