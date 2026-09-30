"""Pakiet RAG.

Laduje zmienne z .env juz przy imporcie pakietu, zeby konfiguracja (model
embeddingowy i jego prefiksy, pozniej takze model LLM) byla spojna miedzy
ingestem, retrievalem i chatbotem - bez recznego podawania zmiennych
srodowiskowych przy kazdym uruchomieniu. load_dotenv() NIE nadpisuje zmiennych
juz ustawionych w powloce, wiec doraznie mozna je nadal nadpisac inline.
"""

from dotenv import load_dotenv

load_dotenv()
