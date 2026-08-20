import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "Chatbot WMI UJ - API"

FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

if not JWT_SECRET:
    raise RuntimeError("Brak JWT_SECRET w .env — ustaw go przed uruchomieniem serwera")