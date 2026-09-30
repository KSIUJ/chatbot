"""
Wspolne wywolania HTTP dla klientow LLM z kluczem w naglowku Bearer
(openrouter_client.py, cursor_client.py): odczyt klucza z env, zapytanie JSON
i zamiana bledow HTTP/sieci na RuntimeError z czytelnym komunikatem.
"""

import os
from dataclasses import dataclass, field

import requests


@dataclass(frozen=True)
class BearerApi:
    """Opis jednego API: adres, zmienna z kluczem i komunikaty bledow."""

    base_url: str
    # nazwa w komunikatach, np. "OpenRouter", "Cursor API"
    label: str
    key_env: str
    missing_key_message: str
    # komunikaty dla konkretnych statusow HTTP (np. 401, 429)
    status_messages: dict[int, str] = field(default_factory=dict)
    # wymusza UTF-8 przy odpowiedziach bez charset w Content-Type
    force_utf8: bool = False

    def api_key(self) -> str:
        key = os.getenv(self.key_env, "").strip()
        if not key:
            raise RuntimeError(self.missing_key_message)
        return key

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key()}",
            "Content-Type": "application/json",
        }

    def raise_for_status(self, response: requests.Response) -> None:
        if response.status_code < 400:
            return
        message = self.status_messages.get(response.status_code)
        if message is not None:
            raise RuntimeError(message)
        raise RuntimeError(
            f"Blad {self.label} (status {response.status_code}): {response.text[:500]}"
        )

    def request(self, method: str, path: str, *, timeout: float, **kwargs) -> dict:
        try:
            response = requests.request(
                method, f"{self.base_url}{path}", headers=self.headers(), timeout=timeout, **kwargs
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Blad polaczenia z {self.label}: {e}") from e
        if self.force_utf8:
            response.encoding = "utf-8"
        self.raise_for_status(response)
        return response.json()


def build_messages(system: str, user: str, history: list[dict] | None) -> list[dict]:
    """Lista wiadomosci w formacie chat completions: system, historia, pytanie."""
    messages = [{"role": "system", "content": system}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user})
    return messages
