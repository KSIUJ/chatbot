import os
import sys

# generate.py w src/backend/llm/ uzywa importu wzglednego "from ..RAG..." -
# zeby to zadzialalo, na sys.path trzeba dodac katalog NADRZEDNY wobec
# src/backend (czyli src/), w odroznieniu od tests/backend/RAG/conftest.py,
# ktory dodaje sam src/backend (bo RAG nie odwoluje sie do niczego wyzej niz
# wlasny pakiet). src/backend nie ma __init__.py, wiec dziala jako "namespace
# package" (PEP 420) - importy "backend.llm.generate" / "backend.RAG.xxx"
# rozwiazuja sie poprawnie.
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
)
sys.path.insert(0, SRC_DIR)
