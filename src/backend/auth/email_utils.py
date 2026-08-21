import random
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from backend.config import SMTP_EMAIL, SMTP_APP_PASSWORD, SMTP_HOST, SMTP_PORT

KOD_WAZNOSC_MINUT = 15


def generuj_kod() -> str:
    return str(random.randint(100000, 999999))


def kod_wygasa() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=KOD_WAZNOSC_MINUT)


def wyslij_maila(odbiorca: str, temat: str, tresc: str) -> None:
    msg = MIMEText(tresc)
    msg["Subject"] = temat
    msg["From"] = SMTP_EMAIL
    msg["To"] = odbiorca

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.send_message(msg)


def wyslij_kod_weryfikacyjny(odbiorca: str, kod: str) -> None:
    wyslij_maila(
        odbiorca,
        "Kod weryfikacyjny — Chatbot WMI UJ",
        f"Twój kod weryfikacyjny: {kod}\nWażny przez {KOD_WAZNOSC_MINUT} minut.",
    )