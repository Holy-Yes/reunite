#!/bin/sh
# Runs once per container start: wait for Postgres, migrate, seed the demo accounts (idempotent,
# safe to run every boot), then hand off to the CMD (uvicorn).
set -e

python - <<'PY'
import os
import sys
import time
from urllib.parse import urlsplit

url = os.environ.get("DATABASE_URL", "")
if url.startswith("postgresql"):
    import psycopg

    p = urlsplit(url.replace("+psycopg", ""))
    for _ in range(60):
        try:
            psycopg.connect(host=p.hostname, port=p.port or 5432, user=p.username, password=p.password, dbname=p.path.lstrip("/"), connect_timeout=2).close()
            break
        except Exception:
            time.sleep(1)
    else:
        print("database never became ready", file=sys.stderr)
        sys.exit(1)
PY

(cd backend && python -m alembic -c alembic.ini upgrade head)

# --light keeps first-boot seeding fast; already-seeded is a safe no-op (exit code 1, swallowed here).
python scripts/seed_demo.py --light || true

exec "$@"
