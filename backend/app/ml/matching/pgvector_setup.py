"""Optional pgvector acceleration: `vector` mirror columns and HNSW indexes next to the canonical bytea embeddings.

    python scripts/enable_pgvector.py            # after `CREATE EXTENSION` is possible (see --build)

The bytea columns stay the source of truth; these mirrors only speed up nearest-neighbour search. Without the
extension everything still works through the in-memory numpy index.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import text

# (table, mirror column, dimension, source bytea column)
MIRRORS = [
    ("items", "text_embedding_vec", 384, "text_embedding"),
    ("items", "clip_text_embedding_vec", 512, "clip_text_embedding"),
    ("item_images", "embedding_vec", 512, "embedding"),
]


def enable(engine) -> list[str]:  # noqa: ANN001
    """Create the extension, the mirror columns and HNSW cosine indexes. Idempotent. Returns what it did."""
    done: list[str] = []
    with engine.begin() as c:
        c.execute(text("create extension if not exists vector"))
        done.append("extension vector")
        for table, col, dim, _ in MIRRORS:
            c.execute(text(f"alter table {table} add column if not exists {col} vector({dim})"))
            c.execute(text(f"create index if not exists ix_{table}_{col}_hnsw on {table} using hnsw ({col} vector_cosine_ops)"))
            done.append(f"{table}.{col}")
    return done


def backfill(engine) -> int:  # noqa: ANN001
    """Fill the mirror columns from the canonical bytea embeddings."""
    n = 0
    with engine.begin() as c:
        for table, col, dim, src in MIRRORS:
            rows = c.execute(text(f"select id, {src} from {table} where {src} is not null and {col} is null")).all()
            for rid, blob in rows:
                v = np.frombuffer(bytes(blob), dtype="<f4")
                if v.size != dim:
                    continue
                lit = "[" + ",".join(f"{float(x):.6f}" for x in v) + "]"
                c.execute(text(f"update {table} set {col} = cast(:v as vector) where id = :id"), {"v": lit, "id": rid})
                n += 1
    return n


def disable(engine) -> None:  # noqa: ANN001
    with engine.begin() as c:
        for table, col, _, _ in MIRRORS:
            c.execute(text(f"drop index if exists ix_{table}_{col}_hnsw"))
            c.execute(text(f"alter table {table} drop column if exists {col}"))
