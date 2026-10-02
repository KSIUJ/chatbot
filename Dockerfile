FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # dane jezykowe Tesseracta z pakietow tesseract-ocr-pol/-eng (Debian 13)
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

WORKDIR /app

# build-essential: czesc zaleznosci RAG (np. chromadb/hnswlib) moze wymagac
# kompilacji, gdy brakuje gotowego wheela. curl: healthcheck w docker-compose.
# tesseract-ocr + dane pol/eng: OCR zeskanowanych PDF-ow w zalacznikach
# (PyMuPDF uzywa wbudowanego Tesseracta, potrzebuje plikow .traineddata).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
        tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# Torch w wersji CPU instalowany PRZED requirements - inaczej
# sentence-transformers pociagnie kilka GB bibliotek CUDA.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r requirements.txt

COPY src/backend ./src/backend
# ingest do bazy RAG (python -m pipeline.ingest.run_ingest); scrapery
# uruchamia sie lokalnie, poza obrazem
COPY pipeline/ingest ./pipeline/ingest
COPY alembic.ini ./
COPY alembic ./alembic

EXPOSE 8000

# Migracje bazy, potem API. Tylko jeden worker - blokady sesji i rozmow
# dzialaja w obrebie jednego procesu.
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn src.backend.main:app --host 0.0.0.0 --port 8000"]
