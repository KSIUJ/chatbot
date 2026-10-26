"""Petla narzedzi w claude_client.stream_chat: tool_use -> wykonanie przez
ToolBox -> tool_result -> dalsza odpowiedz; limit rund i ostatnia runda bez
narzedzi. Modul anthropic to atrapa ze scenariuszem kolejnych odpowiedzi."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from src.backend.llm import claude_client
from src.backend.llm.tools import MAX_ROUNDS, Tool, ToolBox, ToolResult


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use(name, arguments, block_id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=arguments, id=block_id)


class ScriptedStream:
    def __init__(self, texts, content, stop_reason):
        self.texts, self.content, self.stop_reason = texts, content, stop_reason

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        yield from self.texts

    def get_final_message(self):
        return SimpleNamespace(content=self.content, stop_reason=self.stop_reason, stop_details=None)


class ScriptedClient:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.requests = []
        self.messages = self

    def stream(self, **request):
        # kopia: messages rosnie miedzy rundami
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.rounds.pop(0)


@pytest.fixture
def scripted(monkeypatch):
    holder = {}

    def install(*rounds):
        client = ScriptedClient(rounds)
        holder["client"] = client
        module = types.ModuleType("anthropic")
        for name in ("AuthenticationError", "RateLimitError", "APIConnectionError", "APIStatusError"):
            setattr(module, name, type(name, (Exception,), {}))
        monkeypatch.setitem(sys.modules, "anthropic", module)
        monkeypatch.setattr(claude_client, "_client", lambda timeout: (module, client))
        monkeypatch.delenv("CLAUDE_EFFORT", raising=False)
        return client

    return install


def _box(calls):
    def timetable(arguments):
        calls.append(dict(arguments))
        return ToolResult('{"activities":[]}')

    return ToolBox(tools=[Tool("usos_my_timetable", "plan", {"type": "object"}, timetable)])


def test_tool_call_result_goes_back_and_answer_continues(scripted):
    calls = []
    client = scripted(
        ScriptedStream(["Sprawdzam plan."], [_text("Sprawdzam plan."), _tool_use("usos_my_timetable", {"days": 1})], "tool_use"),
        ScriptedStream(["Jutro nie masz zajęć."], [_text("Jutro nie masz zajęć.")], "end_turn"),
    )
    box = _box(calls)

    text = "".join(claude_client.stream_chat("system", "Co mam jutro?", tools=box))

    assert text == "Sprawdzam plan.\n\nJutro nie masz zajęć."
    assert calls == [{"days": 1}]
    first, second = client.requests
    assert first["tools"] == box.definitions() and "tool_choice" not in first
    assistant, results = second["messages"][-2:]
    assert assistant["role"] == "assistant" and assistant["content"][1].name == "usos_my_timetable"
    assert results == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": '{"activities":[]}', "is_error": False},
    ]}
    assert box.used == ["usos_my_timetable"]


def test_last_round_disables_tools(scripted):
    rounds = [
        ScriptedStream([], [_tool_use("usos_my_timetable", {}, f"tu_{i}")], "tool_use") for i in range(MAX_ROUNDS)
    ]
    client = scripted(*rounds, ScriptedStream(["Nie udało się."], [_text("Nie udało się.")], "end_turn"))

    text = "".join(claude_client.stream_chat("system", "plan?", tools=_box([])))

    assert text == "Nie udało się."
    assert len(client.requests) == MAX_ROUNDS + 1
    assert client.requests[-1]["tool_choice"] == {"type": "none"}
    assert all("tool_choice" not in r for r in client.requests[:-1])


def test_without_tools_no_tool_definitions(scripted):
    client = scripted(ScriptedStream(["Cześć"], [_text("Cześć")], "end_turn"))

    assert "".join(claude_client.stream_chat("system", "hej")) == "Cześć"
    assert "tools" not in client.requests[0]
