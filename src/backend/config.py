import os

APP_NAME = "Chatbot WMI UJ - API"

DEFAULT_FRONTEND_ORIGINS = "http://localhost:5173"


def parse_origins(raw: str) -> list[str]:
    """Originy z listy rozdzielonej przecinkami: bez spacji, koncowego "/"
    i pustych pozycji (CORS porownuje originy dokladnie)."""
    origins = (origin.strip().rstrip("/") for origin in raw.split(","))
    return [origin for origin in origins if origin]


# Adresy, z ktorych frontend moze odpytywac backend (w .env kilka po przecinku)
FRONTEND_ORIGINS = parse_origins(os.getenv("FRONTEND_ORIGINS") or DEFAULT_FRONTEND_ORIGINS)
