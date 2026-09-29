from __future__ import annotations

import hashlib
import re

import numpy as np


def normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-8)


def to_bytes(v: np.ndarray | None) -> bytes | None:
    return None if v is None else np.asarray(v, dtype="<f4").tobytes()


def from_bytes(b: bytes | None) -> np.ndarray | None:
    return None if not b else np.frombuffer(b, dtype="<f4").copy()


def hash_embed(text: str, dim: int) -> np.ndarray:
    """Deterministic bag-of-words embedding by feature hashing. Only used when ML_MODE=light."""
    v = np.zeros(dim, dtype=np.float32)
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 20) & 1 else -1.0
    return normalize(v) if v.any() else v
