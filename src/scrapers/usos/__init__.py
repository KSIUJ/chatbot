"""
Scraper USOS UJ -> zbior data/usos/ dla RAG-a (format: src/backend/rag/DATASETS.md).

    python -m src.scrapers.usos                 # caly przebieg
    python -m src.scrapers.usos --only news     # tylko wybrane kolektory (z --partial)
    python -m src.scrapers.usos call services/fac/faculty fac_id=UJ.WMI
    python -m src.scrapers.usos login            # token operatora (e-maile pracownikow)

Dane publiczne z USOS API (api.py) i stron informacyjnych USOSweb (web.py);
klucz aplikacji USOS_CONSUMER_KEY/SECRET z .env odblokowuje wiekszosc metod.
"""
