#!/usr/bin/env python
"""Turn on pgvector acceleration (optional; the numpy index is used automatically without it).

    python scripts/enable_pgvector.py            # create extension, mirror columns, HNSW indexes, backfill
    python scripts/enable_pgvector.py --build    # first compile and install pgvector from source (Homebrew Postgres 16)
    python scripts/enable_pgvector.py --disable

If `create extension` fails, leave it: nothing else needs it.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("JWT_SECRET", "dev")

VERSION = "v0.8.0"


def build() -> None:
    pg_config = shutil.which("pg_config") or "/opt/homebrew/opt/postgresql@16/bin/pg_config"
    if not Path(pg_config).exists():
        sys.exit("pg_config not found. Install Postgres 16 (brew install postgresql@16) first.")
    tmp = Path(tempfile.mkdtemp()) / "pgvector"
    subprocess.check_call(["git", "clone", "--quiet", "--branch", VERSION, "--depth", "1", "https://github.com/pgvector/pgvector.git", str(tmp)])
    env = {**os.environ, "PG_CONFIG": pg_config}
    subprocess.check_call(["make", "-j4"], cwd=tmp, env=env)
    subprocess.check_call(["make", "install"], cwd=tmp, env=env)
    print("pgvector built and installed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--disable", action="store_true")
    args = ap.parse_args()
    if args.build:
        build()
    from app import db as dbmod
    from app.ml.matching import pgvector_setup

    engine = dbmod.configure()
    if engine.dialect.name != "postgresql":
        sys.exit("pgvector needs PostgreSQL (DATABASE_URL points at " + engine.dialect.name + ")")
    if args.disable:
        pgvector_setup.disable(engine)
        print("mirror columns and indexes removed")
        return 0
    try:
        for step in pgvector_setup.enable(engine):
            print("ok:", step)
    except Exception as e:  # noqa: BLE001
        print("could not enable pgvector:", str(e).splitlines()[0], "\nThe numpy index will be used instead.")
        return 1
    print("backfilled", pgvector_setup.backfill(engine), "embeddings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
