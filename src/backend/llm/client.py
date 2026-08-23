import os

import requests

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:14b"


def chat(
    system: str,
    user: str,
    model: str | None = None,
    host: str | None = None,
    temperature: float = 0.2,
    timeout: int = 300,
) -> str:
    model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    host = host or os.getenv("OLLAMA_HOST", DEFAULT_HOST)

    response = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]
