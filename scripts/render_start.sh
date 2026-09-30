#!/bin/sh
# Render start step (runs from the repo root): migrate, seed demo accounts (idempotent), serve.
set -e

# Render hands out postgres:// URLs; SQLAlchemy needs the psycopg 3 driver spelled out.
case "$DATABASE_URL" in
  postgres://*)     DATABASE_URL="postgresql+psycopg://${DATABASE_URL#postgres://}" ;;
  postgresql://*)   DATABASE_URL="postgresql+psycopg://${DATABASE_URL#postgresql://}" ;;
esac
export DATABASE_URL

(cd backend && python -m alembic -c alembic.ini upgrade head)
python scripts/seed_demo.py --light || true

exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "${PORT:-8010}" --workers 1
