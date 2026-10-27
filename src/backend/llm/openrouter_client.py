"""
Klient OpenRouter API, uzywany gdy LLM_PROVIDER=openrouter. Ten sam interfejs
chat(system, user, history=None) -> str i stream_chat(...) -> kawalki tekstu
co ollama_client.py.

OpenRouter wystawia API zgodne z chat completions OpenAI i routuje zapytanie
do wybranego dostawcy, wiec model zmienia sie sama zmienna OPENROUTER_MODEL.
Klient uzywa requests (bez SDK openai).

Narzedzia (llm/tools.py) ida w formacie OpenAI (tools/tool_calls) - petla jak
w claude_client.py: najwyzej MAX_ROUNDS rund, w ostatniej tool_choice "none".
Model bez obslugi narzedzi odpowie bledem API (-> llm_failed).
"""

import json
from collections.abc import Iterator, Sequence
from typing import Any

from .http_api import BearerApi, build_messages
from .images import ImageInput
from .provider import env_setting
from .tools import MAX_ROUNDS, ToolBox

DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_TIMEOUT = 300

_API = BearerApi(
    base_url="https://openrouter.ai/api/v1",
    label="OpenRouter",
    key_env="OPENROUTER_API_KEY",
    missing_key_message=(
        "Brak klucza OpenRouter (OPENROUTER_API_KEY). Wygeneruj go w "
        "https://openrouter.ai/keys i ustaw w .env."
    ),
    status_messages={
        401: "Nieprawidlowy lub brakujacy klucz OpenRouter (OPENROUTER_API_KEY).",
        402: "Brak srodkow na koncie OpenRouter albo model przekracza limit kredytow.",
        429: "Przekroczono limit zapytan do OpenRouter.",
    },
)


def _messages(
    system: str, user: str, history: list[dict[str, str]] | None, images: Sequence[ImageInput] | None
) -> list[dict[str, object]]:
    """Wiadomosci chat completions; z obrazami pytanie ma czesci: tekst
    i obrazy jako adresy data: (format OpenAI, ktory OpenRouter przekazuje
    dalej). Model bez obslugi obrazow zwroci blad API (-> llm_failed)."""
    messages = build_messages(system, user, history)
    if images:
        parts: list[dict[str, object]] = [{"type": "text", "text": user}]
        parts.extend({"type": "image_url", "image_url": {"url": image.data_url()}} for image in images)
        messages[-1] = {"role": "user", "content": parts}
    return messages


def chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = DEFAULT_TIMEOUT,
    images: Sequence[ImageInput] | None = None,
) -> str:
    """Wysyla rozmowe do OpenRouter i zwraca tekst pierwszego wyboru."""
    model = model or env_setting("OPENROUTER_MODEL", DEFAULT_MODEL)

    payload = {
        "model": model,
        "messages": _messages(system, user, history, images),
        "temperature": temperature,
        "stream": False,
    }
    data = _API.request("POST", "/chat/completions", timeout=timeout, json=payload)

    # OpenRouter potrafi odpowiedziec HTTP 200 z bledem w ciele (np. gdy padnie
    # dostawca, do ktorego routuje zapytanie) - wtedy nie ma klucza "choices".
    _raise_on_error(data)

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter zwrocil odpowiedz bez zadnego wyboru (choices).")

    return (choices[0].get("message", {}).get("content") or "").strip()


def stream_chat(
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: int = DEFAULT_TIMEOUT,
    images: Sequence[ImageInput] | None = None,
    tools: ToolBox | None = None,
) -> Iterator[str]:
    """Jak chat(), ale oddaje kawalki odpowiedzi na biezaco (SSE z OpenRouter).
    Zamkniecie generatora zamyka polaczenie.

    `tools` - narzedzia dla modelu; gdy je wywola (finish_reason "tool_calls"),
    wyniki wracaja jako wiadomosci "tool" i model pisze dalej."""
    messages = _messages(system, user, history, images)
    payload: dict[str, Any] = {
        "model": model or env_setting("OPENROUTER_MODEL", DEFAULT_MODEL),
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if tools is not None and tools.tools:
        payload["tools"] = [_tool_definition(definition) for definition in tools.definitions()]
    produced = False
    for round_number in range(MAX_ROUNDS + 1):
        if "tools" in payload and round_number == MAX_ROUNDS:
            payload["tool_choice"] = "none"
        calls: dict[int, dict[str, str]] = {}
        round_text: list[str] = []
        finish = None
        for text, tool_deltas, finish_reason in _stream_round(payload, timeout):
            if text:
                if not round_text and produced:
                    # tekst przed wywolaniem narzedzia i po nim - osobne akapity
                    yield "\n\n"
                round_text.append(text)
                produced = True
                yield text
            for delta in tool_deltas:
                _merge_tool_delta(calls, delta)
            finish = finish_reason or finish
        if tools is None or not calls:
            return
        tool_calls = [
            {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
            for _index, call in sorted(calls.items())
        ]
        messages.append({"role": "assistant", "content": "".join(round_text) or None, "tool_calls": tool_calls})
        for call in tool_calls:
            result = tools.execute(call["function"]["name"], _arguments(call["function"]["arguments"]))
            # format OpenAI nie ma is_error - blad oznaczamy w tresci
            content = f"BŁĄD: {result.content}" if result.is_error else result.content
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})


def _stream_round(payload: dict[str, Any], timeout: int) -> Iterator[tuple[str, list[dict], str | None]]:
    """Jedna odpowiedz modelu (SSE): (tekst, fragmenty tool_calls, finish_reason) na zdarzenie."""
    with _API.stream("POST", "/chat/completions", timeout=timeout, json=payload) as response:
        for raw in response.iter_lines():
            # linie zaczynajace sie od ":" to komentarze podtrzymujace polaczenie
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                return
            event = json.loads(data)
            # blad w trakcie odpowiedzi przychodzi jako zwykle zdarzenie z "error"
            _raise_on_error(event)
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            yield delta.get("content") or "", delta.get("tool_calls") or [], choices[0].get("finish_reason")


def _tool_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Opis narzedzia z formatu Claude (name/description/input_schema) na OpenAI."""
    return {"type": "function", "function": {
        "name": definition["name"], "description": definition["description"], "parameters": definition["input_schema"],
    }}


def _merge_tool_delta(calls: dict[int, dict[str, str]], delta: dict[str, Any]) -> None:
    """Wywolanie narzedzia przychodzi w kawalkach: id i nazwa na poczatku,
    argumenty (JSON) doklejane po kolei; kawalki laczy index."""
    call = calls.setdefault(int(delta.get("index") or 0), {"id": "", "name": "", "arguments": ""})
    function = delta.get("function") or {}
    call["id"] = delta.get("id") or call["id"]
    call["name"] = function.get("name") or call["name"]
    call["arguments"] += function.get("arguments") or ""


def _arguments(raw: str) -> Any:
    """Argumenty wywolania (JSON); zly JSON - ToolBox odrzuci je jako nie-obiekt."""
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return raw


def _raise_on_error(data: dict) -> None:
    error = data.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"Blad OpenRouter: {message}")
