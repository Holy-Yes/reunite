"""Runs only against Postgres with pgvector installed:  TEST_DATABASE_URL=postgresql+psycopg://localhost/reunite_test"""
import os
import uuid

import numpy as np
import pytest

from app import db as dbmod
from app.ml.embed_util import to_bytes
from app.ml.matching import pgvector_setup
from app.ml.matching.index import PgVectorIndex, has_pgvector
from tests import factories as fx

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs Postgres")


@pytest.fixture()
def pg(db):
    engine = dbmod.engine
    try:
        pgvector_setup.enable(engine)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"pgvector unavailable: {e}")
    assert has_pgvector(engine)
    yield engine
    pgvector_setup.disable(engine)


def test_pgvector_index_matches_numpy_ranking(db, pg):
    from app.ml.matching.index import NumpyIndex

    u = fx.user(db, "a@x.edu")
    rng = np.random.default_rng(3)
    items, vecs = [], {}
    for i in range(12):
        it = fx.item(db, u, "found", "laptop")
        v = rng.standard_normal(384).astype(np.float32)
        it.text_embedding = to_bytes(v / np.linalg.norm(v))
        items.append(it)
        vecs[str(it.id)] = v
    db.commit()
    assert pgvector_setup.backfill(pg) == 12

    pgi = PgVectorIndex(pg, "items", "text_embedding_vec", 384)
    npi = NumpyIndex(384)
    for k, v in vecs.items():
        npi.upsert(k, v)
    q = vecs[str(items[4].id)] + 0.05 * rng.standard_normal(384).astype(np.float32)
    a, b = pgi.search(q, 5), npi.search(q, 5)
    assert [k for k, _ in a] == [k for k, _ in b] and a[0][0] == str(items[4].id)
    assert a[0][1] == pytest.approx(b[0][1], abs=1e-4)

    allowed = [str(items[1].id), str(items[2].id), str(items[3].id)]
    assert {k for k, _ in pgi.search(q, 5, allowed=allowed)} == set(allowed)
    assert pgi.search(q, 5, allowed=[]) == []
    pgi.remove(str(items[4].id))
    assert str(items[4].id) not in [k for k, _ in pgi.search(q, 12)]
    pgi.upsert(str(items[4].id), q)
    assert pgi.search(q, 1)[0][0] == str(items[4].id)


def test_enable_is_idempotent(pg):
    assert pgvector_setup.enable(pg)
    assert pgvector_setup.enable(pg)
