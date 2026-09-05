#!/bin/sh
set -e

echo "[entrypoint] alembic upgrade head..."
python -m alembic upgrade head

echo "[entrypoint] start uvicorn..."
exec uvicorn src.backend.main:app --host 0.0.0.0 --port 8000
