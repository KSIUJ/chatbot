FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # dane jezykowe Tesseracta z pakietow tesseract-ocr-pol/-eng (Debian 13)
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata \
    # model embeddingow (wolumen hf-cache) poza /root - backend dziala jako "app"
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# build-essential: czesc zaleznosci RAG (np. chromadb/hnswlib) moze wymagac
# kompilacji, gdy brakuje gotowego wheela. curl: healthcheck w docker-compose.
# tesseract-ocr + dane pol/eng: OCR zeskanowanych PDF-ow w zalacznikach
# (PyMuPDF uzywa wbudowanego Tesseracta, potrzebuje plikow .traineddata).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
        tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Obraz budowany z katalogu glownego repo: build: context . i
# dockerfile: deploy/Dockerfile w docker-compose.yml.
# Zaleznosci: grupa "app" z pyproject.toml ([dependency-groups]); pyproject.toml
# niesie tez konfiguracje alembica ([tool.alembic]).
COPY pyproject.toml ./
COPY deploy/constraints.txt ./deploy/
# Torch w wersji CPU instalowany PRZED reszta - inaczej sentence-transformers
# pociagnie kilka GB bibliotek CUDA. Wersje przypiete (deploy/constraints.txt =
# pip freeze obrazu), aktualizacja: komentarz w pyproject.toml.
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --group app -c deploy/constraints.txt

# Uzytkownik bez uprawnien; docker-entrypoint.sh przechodzi na niego po
# poprawieniu wlasciciela wolumenow.
RUN useradd --system --uid 10001 --user-group --home-dir /app --no-create-home app
COPY deploy/docker-entrypoint.sh /usr/local/bin/

# backend z migracjami (src/backend/migrations) i notatkami o KSI
# (src/backend/rag/sources/ksi/content); scrapery (src/scrapers) nie wchodza
# do obrazu - deploy/refresh-usos.sh montuje je z repozytorium
COPY src/backend ./src/backend

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]

# Migracje bazy, potem API. Tylko jeden worker - blokady sesji i rozmow
# dzialaja w obrebie jednego procesu.
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn src.backend.main:app --host 0.0.0.0 --port 8000"]
