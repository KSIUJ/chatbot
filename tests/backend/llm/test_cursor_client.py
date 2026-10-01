"""
Testy stream_chat w cursor_client.py - Cursor nie ma API strumieniowego,
wiec cala odpowiedz przychodzi jako jeden kawalek.
"""

from src.backend.llm import cursor_client


def test_stream_chat_yields_whole_answer_once(monkeypatch):
    seen = {}

    def fake_chat(system, user, history=None):
        seen.update(system=system, user=user, history=history)
        return "pelna odpowiedz"

    monkeypatch.setattr(cursor_client, "chat", fake_chat)
    history = [{"role": "user", "content": "hej"}]

    chunks = list(cursor_client.stream_chat(system="s", user="u", history=history))

    assert chunks == ["pelna odpowiedz"]
    assert seen == {"system": "s", "user": "u", "history": history}


def test_stream_chat_yields_nothing_for_empty_answer(monkeypatch):
    monkeypatch.setattr(cursor_client, "chat", lambda system, user, history=None: "")

    assert list(cursor_client.stream_chat(system="s", user="u")) == []
