FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# build-essential: część zaleznosci RAG (np. chromadb/hnswlib) potrafi
# wymagac kompilacji przy braku gotowego wheela dla danej platformy.
# curl: healthcheck w docker-compose.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# CPU-only torch (kilkaset MB) zamiast domyslnej paczki z PyPI, ktora na
# Linuksie x86_64 ciagnie kilka GB bibliotek CUDA (nvidia-cublas, cudnn,
# nvJitLink...) kompletnie zbednych bez GPU - instalowana PRZED requirements
# tak, zeby pip przy sentence-transformers zobaczyl juz spelniona zaleznosc
# i nie podmienil jej na wariant z CUDA.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r requirements.txt

COPY src/backend ./src/backend
COPY alembic.ini ./
COPY alembic ./alembic

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
