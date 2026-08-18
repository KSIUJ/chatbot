import os

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "Chatbot WMI UJ - API"

# Adresy, z ktorych frontend moze odpytywac backend
# W .env mozna podac kilka adresow oddzielonych przecinkiem.
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
