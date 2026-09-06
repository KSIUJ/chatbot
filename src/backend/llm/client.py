import os

import requests

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:14b"
DEFAULT_NUM_CTX = 8192


def chat(
    system: str,
    user: str,
    history: list[dict] | None = None,
    model: str | None = None,
    host: str | None = None,
    temperature: float = 0.2,
    timeout: int = 300,
    num_ctx: int | None = None,
) -> str:
    model = model or os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL
    host = host or os.getenv("OLLAMA_HOST") or DEFAULT_HOST
    num_ctx = num_ctx or int(os.getenv("OLLAMA_NUM_CTX") or DEFAULT_NUM_CTX)

    messages = [{"role": "system", "content": system}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user})

    response = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]
