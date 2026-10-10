import os

APP_NAME = "Chatbot WMI UJ - API"

# Frontend z vite (npm run dev) - domyslny origin tylko przy logowaniu po http,
# czyli lokalnie; w produkcji (OIDC_REDIRECT_URI po https) domyslnie zaden.
DEV_FRONTEND_ORIGINS = "http://localhost:5173"


def default_frontend_origins(redirect_uri: str) -> str:
    return "" if redirect_uri.startswith("https://") else DEV_FRONTEND_ORIGINS


def parse_origins(raw: str) -> list[str]:
    """Originy z listy rozdzielonej przecinkami: bez spacji, koncowego "/"
    i pustych pozycji (CORS porownuje originy dokladnie)."""
    origins = (origin.strip().rstrip("/") for origin in raw.split(","))
    return [origin for origin in origins if origin]


# Adresy, z ktorych frontend moze odpytywac backend (w .env kilka po przecinku)
FRONTEND_ORIGINS = parse_origins(
    os.getenv("FRONTEND_ORIGINS") or default_frontend_origins(os.getenv("OIDC_REDIRECT_URI", ""))
)

# /docs, /redoc i /openapi.json tylko na zyczenie (API_DOCS=true) - w produkcji
# nie pokazujemy listy endpointow, takze tych dla zarzadu.
API_DOCS = os.getenv("API_DOCS", "").strip().lower() in {"1", "true", "yes", "on"}
