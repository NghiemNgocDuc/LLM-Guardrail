#!/bin/sh
set -e

echo "Running startup preflight..."
python -m app.preflight

echo "Running database migrations..."
alembic upgrade head

echo "Starting API server on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}"
