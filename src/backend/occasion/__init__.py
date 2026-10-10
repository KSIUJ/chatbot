"""Motywy okazjonalne: czat zmienia wyglad razem ze strona glowna KSI (ksi.sh).

O tym, czy i jaki motyw trwa, decyduje wylacznie ksi.sh - w repozytorium nie
ma motywow, terminow ani grafik (konkurs odznak KSI). Backend czyta stan ze
strony w tle (state.py), sprawdza fasade SVG (svg.py) i podaje ja z naszego
originu (router.py), wiec CSP frontendu zostaje bez zmian.
"""

from .router import router

__all__ = ["router"]
