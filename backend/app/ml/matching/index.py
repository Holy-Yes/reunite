"""Vector index behind one interface. pgvector (HNSW, cosine) when the extension exists, else an
in-memory numpy brute-force index, rebuilt from the stored bytes at startup. Campus scale (under
10,000 items) makes brute force fast enough."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable

import numpy as np

log = logging.getLogger("reunite.index")


class VectorIndex(ABC):
    @abstractmethod
    def upsert(self, key: str, vec: np.ndarray) -> None: ...

    @abstractmethod
    def remove(self, key: str) -> None: ...

    @abstractmethod
    def search(self, query: np.ndarray, k: int, allowed: Iterable[str] | None = None) -> list[tuple[str, float]]:
        """[(key, cosine)] best first, restricted to `allowed` keys when given."""


class NumpyIndex(VectorIndex):
    def __init__(self, dim: int):
        self.dim = dim
        self._keys: list[str] = []
        self._pos: dict[str, int] = {}
        self._mat = np.zeros((0, dim), dtype=np.float32)

    def __len__(self) -> int:
        return len(self._keys)

    def upsert(self, key: str, vec: np.ndarray) -> None:
        v = np.asarray(vec, dtype=np.float32)
        v = v / max(float(np.linalg.norm(v)), 1e-8)
        if key in self._pos:
            self._mat[self._pos[key]] = v
            return
        self._pos[key] = len(self._keys)
        self._keys.append(key)
        self._mat = np.vstack([self._mat, v[None, :]])

    def remove(self, key: str) -> None:
        i = self._pos.pop(key, None)
        if i is None:
            return
        last = len(self._keys) - 1
        if i != last:
            self._keys[i] = self._keys[last]
            self._mat[i] = self._mat[last]
            self._pos[self._keys[i]] = i
        self._keys.pop()
        self._mat = self._mat[:last]

    def search(self, query: np.ndarray, k: int, allowed: Iterable[str] | None = None) -> list[tuple[str, float]]:
        if not self._keys:
            return []
        q = np.asarray(query, dtype=np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-8)
        if allowed is None:
            rows = np.arange(len(self._keys))
        else:
            rows = np.array([self._pos[a] for a in allowed if a in self._pos], dtype=int)
            if rows.size == 0:
                return []
        sims = self._mat[rows] @ q
        top = np.argsort(-sims)[:k]
        return [(self._keys[int(rows[i])], float(sims[i])) for i in top]


def has_pgvector(engine) -> bool:  # noqa: ANN001
    """True when the connected Postgres has the `vector` extension installed and enabled."""
    if engine.dialect.name != "postgresql":
        return False
    from sqlalchemy import text

    try:
        with engine.connect() as c:
            return c.execute(text("select 1 from pg_extension where extname = 'vector'")).first() is not None
    except Exception:  # noqa: BLE001
        return False


class PgVectorIndex(VectorIndex):
    """Cosine search over `vector` mirror columns added by `scripts/enable_pgvector.py`. The bytea
    columns stay the canonical copy; this only accelerates nearest-neighbour lookups."""

    def __init__(self, engine, table: str, column: str, dim: int):  # noqa: ANN001
        self.engine, self.table, self.column, self.dim = engine, table, column, dim

    def _lit(self, v: np.ndarray) -> str:
        return "[" + ",".join(f"{float(x):.6f}" for x in v) + "]"

    def upsert(self, key: str, vec: np.ndarray) -> None:
        from sqlalchemy import text

        with self.engine.begin() as c:
            c.execute(text(f"update {self.table} set {self.column} = cast(:v as vector) where id = cast(:k as uuid)"), {"v": self._lit(vec), "k": key})

    def remove(self, key: str) -> None:
        from sqlalchemy import text

        with self.engine.begin() as c:
            c.execute(text(f"update {self.table} set {self.column} = null where id = cast(:k as uuid)"), {"k": key})

    def search(self, query: np.ndarray, k: int, allowed: Iterable[str] | None = None) -> list[tuple[str, float]]:
        from sqlalchemy import text

        where = f"{self.column} is not null"
        params: dict = {"q": self._lit(query), "k": k}
        if allowed is not None:
            ids = list(allowed)
            if not ids:
                return []
            where += " and id = any(cast(:ids as uuid[]))"
            params["ids"] = ids
        sql = f"select cast(id as text), 1 - ({self.column} <=> cast(:q as vector)) from {self.table} where {where} order by {self.column} <=> cast(:q as vector) limit :k"
        with self.engine.connect() as c:
            return [(r[0], float(r[1])) for r in c.execute(text(sql), params)]
