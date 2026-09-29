"""Sentence embeddings for text-to-text similarity (MiniLM, 384 dimensions)."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from ...config import get_settings
from .. import registry
from ..embed_util import hash_embed, normalize

DIM = 384
MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache
def _model():
    registry.setup_cache_dirs()
    from sentence_transformers import SentenceTransformer

    m = SentenceTransformer(MODEL, device=registry.device())
    registry.note("text_embedder", f"MiniLM-L6 on {registry.device()}")
    return m


def embed_texts(texts: list[str]) -> np.ndarray:
    """(n, 384) float32, L2-normalized."""
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    if get_settings().light_ml:
        registry.note("text_embedder", "light (hashing)")
        return np.stack([hash_embed(t, DIM) for t in texts])
    out = registry.call_ml(lambda: _model().encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False))
    return normalize(out)


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]
