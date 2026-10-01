"""
Klient Cursor Cloud Agents API, uzywany gdy LLM_PROVIDER=cursor. Ten sam
interfejs chat(system, user, history=None) -> str co ollama_client.py;
stream_chat oddaje cala odpowiedz jednym kawalkiem (brak API strumieniowego).

Cursor nie ma synchronicznego API inferencji: kazde chat() tworzy nowego
agenta bez repo i odpytuje o wynik runa. Odpowiedz trwa dziesiatki sekund, a
rownolegle wywolania na tego samego agenta zwracaja 409 - nadaje sie tylko na
demo z jednym uzytkownikiem naraz. Model ustawia CURSOR_MODEL.
"""

import time
from collections.abc import Iterator

from .http_api import BearerApi
from .provider import env_setting

DEFAULT_MODEL = "claude-haiku-4-5"
# Limit czasu (s) uzywany dwa razy: jako timeout samego POST /v1/agents (potrafi
# blokowac ~60 s) i osobno jako limit pollingu statusu po jego zakonczeniu.
DEFAULT_TIMEOUT = 600
DEFAULT_POLL_INTERVAL = 2.0
# Timeout pojedynczego GET statusu runa.
_HTTP_TIMEOUT = 60

# Statusy runa, po ktorych nie ma sensu dalej pollowac.
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
    # Cursor zwraca JSON bez charset w Content-Type - bez tego requests myli
    # polski UTF-8 z CP1250 ("mogę" -> "mogÄ™").
    force_utf8=True,
)


def _extract_result_text(result: object) -> str:
    # GET run zwraca "result" jako string; obsluz tez ksztalt {"text": ...}
    # znany ze zdarzen streamingu.
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("text", "")
    return ""


def _build_prompt(system: str, user: str, history: list[dict[str, str]] | None) -> str:
    # Cursor ma jedno pole prompt.text (bez rol), wiec instrukcja systemowa,
    # historia i pytanie trafiaja do jednego tekstu.
    sections = [system] if system else []
    for message in history or []:
        speaker = "Uzytkownik" if message.get("role") == "user" else "Asystent"
        content = message.get("content") or ""
        if content:
            sections.append(f"{speaker}: {content}")
    sections.append(user)
    return "\n\n".join(sections)


def chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> str:
    """Uruchamia agenta Cursor z promptem i czeka na wynik runa."""
    model = model or env_setting("CURSOR_MODEL", DEFAULT_MODEL)

    created = _API.request(
        "POST",
        "/v1/agents",
        timeout=timeout,
        json={"prompt": {"text": _build_prompt(system, user, history)}, "model": {"id": model}},
    )
    agent_id = created["agent"]["id"]
    run_id = created["run"]["id"]

    deadline = time.monotonic() + timeout
    while True:
        run = _API.request("GET", f"/v1/agents/{agent_id}/runs/{run_id}", timeout=_HTTP_TIMEOUT)
        status = run.get("status")

        if status == "FINISHED":
            return _extract_result_text(run.get("result")).strip()
        if status in _TERMINAL_STATUSES:
            raise RuntimeError(f"Agent Cursor zakonczyl sie ze statusem {status}.")
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Przekroczono limit czasu ({timeout}s) oczekiwania na odpowiedz "
                f"agenta Cursor (ostatni status: {status})."
            )

        time.sleep(poll_interval)


def stream_chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
) -> Iterator[str]:
    """Cursor nie strumieniuje - cala odpowiedz z chat() jako jeden kawalek."""
    reply = chat(system=system, user=user, history=history)
    if reply:
        yield reply
