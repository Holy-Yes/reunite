"""Tests run on in-memory SQLite with ML_MODE=light (tiny deterministic stand-ins, no model downloads)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ["ML_MODE"] = "light"
os.environ["DISABLE_WORKER"] = "1"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EMAIL_BACKEND"] = "console"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shutil
import tempfile

import pytest

_media = tempfile.mkdtemp(prefix="reunite-test-media-")
os.environ["MEDIA_DIR"] = _media

from app import db as dbmod  # noqa: E402
from app.config import reset_settings  # noqa: E402

reset_settings()


@pytest.fixture()
def db():
    from app import models  # noqa: F401
    from app.services.handover import reset_attempts
    from app.services.zones import load_zones

    url = os.environ.get("TEST_DATABASE_URL", "sqlite://")   # e.g. postgresql+psycopg://localhost/reunite_test
    dbmod.configure(url)
    dbmod.Base.metadata.drop_all(dbmod.engine)
    dbmod.Base.metadata.create_all(dbmod.engine)
    reset_attempts()
    from app.services.tags import reset_limits

    reset_limits()
    session = dbmod.SessionLocal()
    load_zones(session)
    yield session
    session.close()
    dbmod.Base.metadata.drop_all(dbmod.engine)


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    from app.db import get_db

    app.dependency_overrides[get_db] = lambda: (yield db)
    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001
    shutil.rmtree(_media, ignore_errors=True)
