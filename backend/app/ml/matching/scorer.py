"""Weighted score with masking, the "why" breakdown, and the calibrated variant.

    raw      = sum(w_i s_i m_i) / sum(w_i m_i)
    coverage = sum(w_i m_i)
    score    = raw * (0.5 + 0.5 * coverage)         less evidence, less confidence
    share_i  = score * (w_i s_i m_i) / sum_j(w_j s_j m_j)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ...config import get_settings
from .features import FEATURES, Feature

WEIGHTS = {
    "category": 0.18,
    "color": 0.12,
    "brand": 0.10,
    "image": 0.18,
    "text": 0.10,
    "cross_modal": 0.08,
    "marks": 0.06,
    "zone": 0.10,
    "time": 0.08,
}
MASK_TERMS = ["image", "text", "cross_modal", "brand", "marks"]  # extra calibration inputs
HAND_VERSION = "hand-v1"

STATE_MATCH, STATE_PARTIAL = 0.85, 0.40


@dataclass
class ScoreResult:
    score: float
    raw: float
    coverage: float
    band: str
    contributions: list[dict]
    model_version: str


def band_for(score: float) -> str:
    s = get_settings()
    return "strong" if score >= s.band_strong else "possible" if score >= s.band_possible else "long_shot"


def _state(f: Feature) -> str:
    if not f.mask:
        return "not_compared"
    return "match" if f.value >= STATE_MATCH else "partial" if f.value >= STATE_PARTIAL else "mismatch"


def _detail(f: Feature) -> str:
    if not f.mask:
        return f"Not compared ({f.note})" if f.note else "Not compared"
    return f.detail


def feature_vector(features: list[Feature]) -> list[float]:
    """x for the calibrated model: s_i * m_i for each feature, then mask indicators."""
    by = {f.key: f for f in features}
    return [by[k].value * (1.0 if by[k].mask else 0.0) for k in FEATURES] + [1.0 if by[k].mask else 0.0 for k in MASK_TERMS]


@lru_cache
def load_calibration(path: str | None = None) -> dict | None:
    p = Path(path) if path else get_settings().weights_path / "calibration.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def reload_calibration() -> None:
    load_calibration.cache_clear()


USE_DEFAULT = object()


def score_pair(features: list[Feature], calibration: dict | None | object = USE_DEFAULT) -> ScoreResult:
    """`calibration`: omitted = the shipped weights/calibration.json if present; None = the hand-set scorer; a dict = that model."""
    calibration = load_calibration() if calibration is USE_DEFAULT else calibration
    by = {f.key: f for f in features}
    w_used = {k: WEIGHTS[k] * (1.0 if by[k].mask else 0.0) for k in FEATURES}
    coverage = sum(w_used.values())
    terms = {k: w_used[k] * by[k].value for k in FEATURES}
    denom = sum(terms.values())
    raw = denom / coverage if coverage > 0 else 0.0

    if calibration:
        x = feature_vector(features)
        coef, b = calibration["coef"], calibration["intercept"]
        z = b + sum(c * xi for c, xi in zip(coef, x))
        score = 1.0 / (1.0 + math.exp(-z))
        pos = {k: max(0.0, coef[i] * x[i]) for i, k in enumerate(FEATURES)}
        pos_sum = sum(pos.values())
        shares = {k: (score * pos[k] / pos_sum if pos_sum > 0 else 0.0) for k in FEATURES}
        version = calibration.get("model_version", "calibrated")
        weights_used = {k: abs(coef[i]) for i, k in enumerate(FEATURES)}
    else:
        score = raw * (0.5 + 0.5 * coverage)
        shares = {k: (score * terms[k] / denom if denom > 0 else 0.0) for k in FEATURES}
        version = HAND_VERSION
        weights_used = WEIGHTS

    contributions = [
        {
            "key": f.key,
            "label": f.label,
            "weight": round(weights_used[f.key], 4),
            "value": round(f.value, 4),
            "contribution": round(shares[f.key], 4),
            "state": _state(f),
            "detail": _detail(f),
        }
        for f in features
    ]
    score = float(min(1.0, max(0.0, score)))
    return ScoreResult(score=score, raw=raw, coverage=coverage, band=band_for(score), contributions=contributions, model_version=version)
