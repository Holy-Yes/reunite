"""Candidate generation: the opposite pool, gated by status, category group and time, then the top N
by the best available embedding similarity (image-image, text-text or text-image)."""
from __future__ import annotations

import numpy as np

from ...config import get_settings
from . import features as F

ELIGIBLE_STATUS = ("open", "matched")
LOW_CONFIDENCE = 0.5   # below this much classified probability, a side's category is too unsure to gate on
MIN_GROUP_OVERLAP = 0.10


def group_overlap(a: F.ItemView, b: F.ItemView) -> float:
    """Probability that the two items fall in the same category group, given each side's category guesses."""
    from ... import taxonomy

    return sum(
        x * y
        for i, x in a.dist.items()
        for j, y in b.dist.items()
        if taxonomy.category_group(i) and taxonomy.category_group(i) == taxonomy.category_group(j)
    )


def passes_gates(query: F.ItemView, cand: F.ItemView) -> bool:
    """Category group (relaxed when a side is unsure of its own category), then the time gate."""
    unsure = min(sum(query.dist.values()), sum(cand.dist.values())) < LOW_CONFIDENCE
    if not (group_overlap(query, cand) >= MIN_GROUP_OVERLAP or unsure):
        return False
    lost, found = (query, cand) if query.kind == "lost" else (cand, query)
    return found.occurred_from >= lost.occurred_from


def embedding_similarity(a: F.ItemView, b: F.ItemView) -> float | None:
    """Best mapped similarity across whatever modalities both sides have; None when neither exists."""

    def cos(x: np.ndarray, y: np.ndarray) -> float:
        return float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-8))

    scores: list[float] = []
    if a.image_embs and b.image_embs:
        scores.append(F.clip01((max(cos(x, y) for x in a.image_embs for y in b.image_embs) - F.IMAGE_LO) / (F.IMAGE_HI - F.IMAGE_LO)))
    if a.text_emb is not None and b.text_emb is not None:
        scores.append(F.clip01((cos(a.text_emb, b.text_emb) - F.TEXT_LO) / (F.TEXT_HI - F.TEXT_LO)))
    for t, im in ((a, b), (b, a)):
        if t.clip_text_emb is not None and im.image_embs:
            scores.append(F.clip01((max(cos(t.clip_text_emb, e) for e in im.image_embs) - F.CROSS_LO) / (F.CROSS_HI - F.CROSS_LO)))
    return max(scores) if scores else None


def top_candidates(query: F.ItemView, pool: list[F.ItemView], k: int | None = None) -> list[F.ItemView]:
    """Gate, then rank by embedding similarity. Items with no embeddings fall back to recency
    (newer first) and rank after items that have a real similarity."""
    k = k or get_settings().candidate_pool
    gated = [c for c in pool if c.id != query.id and passes_gates(query, c)]
    scored: list[tuple[float, float, F.ItemView]] = []
    for c in gated:
        sim = embedding_similarity(query, c)
        recency = c.occurred_from.timestamp()
        scored.append((sim if sim is not None else -1.0, recency, c))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [c for _, _, c in scored[:k]]
