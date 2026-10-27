"""Narzedzia dla modelu (tool use): zamknieta lista funkcji tylko do odczytu,
ktore model moze wywolac w trakcie odpowiedzi - np. plan zajec osoby z USOS
(usos/tools.py). Dostawca, ktory obsluguje narzedzia (claude_client.py),
wykonuje je przez ToolBox.execute i oddaje modelowi wynik jako dane.

ToolBox pilnuje limitow (najwyzej MAX_CALLS wywolan na pytanie), lapie bledy
narzedzi (model dostaje komunikat zamiast wyjatku) i zapamietuje, czego
uzyto - po odpowiedzi chat_stream.py oznacza na tej podstawie odpowiedz jako
oparta na danych osobowych i dodaje zrodlo.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# najwiecej wywolan narzedzi w jednej odpowiedzi i rund model -> narzedzia -> model
MAX_CALLS = 6
MAX_ROUNDS = 3
# wynik narzedzia jest przycinany - nie zalewamy kontekstu modelu
MAX_RESULT_CHARS = 12000


@dataclass(frozen=True)
class ToolResult:
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    # JSON Schema argumentow (type: object)
    input_schema: Mapping[str, Any]
    run: Callable[[Mapping[str, Any]], ToolResult] = field(repr=False, compare=False)

    def definition(self) -> dict[str, Any]:
        """Opis narzedzia w formacie API (Claude: name/description/input_schema)."""
        return {"name": self.name, "description": self.description, "input_schema": dict(self.input_schema)}


@dataclass
class ToolBox:
    tools: list[Tool]
    # dopisek do promptu systemowego, gdy narzedzia sa dostepne
    prompt: str = ""
    # zrodla do pokazania pod odpowiedzia, gdy uzyto narzedzi (kind/title/url)
    citations: list[dict[str, str | None]] = field(default_factory=list)
    # nazwy wywolanych narzedzi (z udanym wynikiem), w kolejnosci
    used: list[str] = field(default_factory=list)
    calls: int = 0

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.definition() for tool in self.tools]

    def execute(self, name: str, arguments: Any) -> ToolResult:
        """Wywolanie narzedzia przez model. Nieznane narzedzie, zle argumenty,
        przekroczony limit albo blad - komunikat dla modelu, nigdy wyjatek."""
        self.calls += 1
        if self.calls > MAX_CALLS:
            return ToolResult("Limit wywołań narzędzi w tej odpowiedzi został wyczerpany.", is_error=True)
        tool = next((t for t in self.tools if t.name == name), None)
        if tool is None:
            return ToolResult(f"Nieznane narzędzie: {name}.", is_error=True)
        if not isinstance(arguments, Mapping):
            return ToolResult("Argumenty narzędzia muszą być obiektem.", is_error=True)
        try:
            result = tool.run(arguments)
        except Exception:
            logger.exception("tool %s failed", name)
            return ToolResult("Narzędzie zawiodło. Powiedz użytkownikowi, że teraz nie da się pobrać tych danych.", is_error=True)
        if not result.is_error and name not in self.used:
            self.used.append(name)
        content = result.content
        if len(content) > MAX_RESULT_CHARS:
            content = content[:MAX_RESULT_CHARS] + "\n[... wynik przycięty]"
        return ToolResult(content, result.is_error)


def as_data(payload: Any) -> str:
    """Wynik narzedzia jako JSON (kompaktowy, z polskimi znakami)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
