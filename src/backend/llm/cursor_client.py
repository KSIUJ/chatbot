"""
Klient Cursor Cloud Agents API - alternatywa dla lokalnego Ollamy (client.py),
Claude API (claude_client.py) i OpenRouter (openrouter_client.py), uzywana gdy
LLM_PROVIDER=cursor (patrz
generate.py). Ten sam interfejs chat(system, user, history=None) -> str, zeby
generate.py mogl przelaczac providera bez zmian w logice RAG.

UWAGA: Cursor nie udostepnia synchronicznego API inferencji. Cloud Agents API
uruchamia agenta w chmurze (provisioning VM), wiec pojedyncze zapytanie trwa
realnie dziesiatki sekund, a rownolegle wywolania na tego samego agenta zwracaja
409. Rozwiazanie akceptowalne tylko na demo z jednym uzytkownikiem naraz.
Kazde wywolanie chat() tworzy nowego, bezstanowego agenta bez repo
("no-repo agent") i odpytuje o wynik w petli.

Model domyslny: "claude-haiku-4-5" (zweryfikowane przez GET /v1/models na
realnym kluczu). Inne dostepne ID sprawdzisz przez cursor_client.list_models();
nadpiszesz przez CURSOR_MODEL w .env.
"""

import os
import time

from .http_api import BearerApi

DEFAULT_MODEL = "claude-haiku-4-5"
# Calkowity budzet czasu na jedno chat() (create + polling). Cursor jest wolny:
# samo POST /v1/agents potrafi blokowac ~60 s (czeka na zakonczenie runa).
DEFAULT_TIMEOUT = 600
DEFAULT_POLL_INTERVAL = 2.0
# Timeout pojedynczego GET (polling statusu runa). POST /v1/agents dostaje
# osobny, dluzszy timeout (parametr `timeout` funkcji chat()).
_HTTP_TIMEOUT = 60

# Statusy runa, po ktorych nie ma sensu dalej pollowac (patrz dokumentacja
# GET /v1/agents/{id}/runs/{runId}).
_TERMINAL_STATUSES = {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}


_API = BearerApi(
    base_url="https://api.cursor.com",
    label="Cursor API",
    key_env="CURSOR_API_KEY",
    missing_key_message=(
        "Brak klucza Cursor API (CURSOR_API_KEY). Wygeneruj go w "
        "https://cursor.com/dashboard/api i ustaw w .env."
    ),
    status_messages={
        401: "Nieprawidlowy lub brakujacy klucz Cursor API (CURSOR_API_KEY).",
        429: "Przekroczono limit zapytan do Cursor API.",
    },
    # Cursor zwraca JSON bez charset w Content-Type - bez tego autodetekcja
    # requests/charset-normalizer myli polski UTF-8 z CP1250 (mojibake w
    # odpowiedziach: "mogę" -> "mogÄ™").
    force_utf8=True,
)


def _request(method: str, path: str, *, timeout: float = _HTTP_TIMEOUT, **kwargs) -> dict:
    return _API.request(method, path, timeout=timeout, **kwargs)


def _extract_result_text(result) -> str:
    # GET run zwraca "result" jako string; na wszelki wypadek obsluz tez ksztalt
    # {"text": ...} znany ze zdarzen streamingu.
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("text", "")
    return ""


def list_models() -> list[str]:
    """Zwraca ID modeli dostepnych w Cloud Agents API (GET /v1/models) -
    pomocne do ustalenia poprawnej wartosci CURSOR_MODEL."""
    data = _request("GET", "/v1/models")
    return [item["id"] for item in data.get("items", [])]


def chat(
    system: str,
    user: str,
    history: list[dict] | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> str:
    model = model or os.getenv("CURSOR_MODEL") or DEFAULT_MODEL

    # Cursor ma jedno pole prompt.text (brak osobnych rol i historii) - skladamy
    # instrukcje systemowa, wczesniejsze tury rozmowy i biezace pytanie w jeden
    # tekst.
    sections = [system] if system else []
    for message in history or []:
        speaker = "Uzytkownik" if message.get("role") == "user" else "Asystent"
        content = message.get("content") or ""
        if content:
            sections.append(f"{speaker}: {content}")
    sections.append(user)
    prompt_text = "\n\n".join(sections)

    # POST /v1/agents blokuje sie, dopoki run sie nie skonczy (~60 s+), wiec
    # dostaje pelny budzet czasu zamiast domyslnego _HTTP_TIMEOUT.
    created = _request(
        "POST",
        "/v1/agents",
        timeout=timeout,
        json={"prompt": {"text": prompt_text}, "model": {"id": model}},
    )
    agent_id = created["agent"]["id"]
    run_id = created["run"]["id"]

    deadline = time.monotonic() + timeout
    last_status: str | None = None
    while True:
        run = _request("GET", f"/v1/agents/{agent_id}/runs/{run_id}")
        last_status = run.get("status")

        if last_status == "FINISHED":
            return _extract_result_text(run.get("result")).strip()
        if last_status in _TERMINAL_STATUSES:  # ERROR / CANCELLED / EXPIRED
            raise RuntimeError(
                f"Agent Cursor zakonczyl sie ze statusem {last_status}."
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Przekroczono limit czasu ({timeout}s) oczekiwania na odpowiedz "
                f"agenta Cursor (ostatni status: {last_status})."
            )

        time.sleep(poll_interval)
