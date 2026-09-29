"""Fit a logistic calibration on labelled pairs, and measure it (ECE, reliability bins).

Positives are true pairs; negatives are the hard negatives from candidate generation. Fitting uses
the 70% split of pair ids, and ECE is reported on the held-out 30%.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from .features import FEATURES
from .scorer import MASK_TERMS


def fit(X: np.ndarray, y: np.ndarray, C: float = 1.0, seed: int = 0) -> dict:
    """L2 logistic regression. Returns the calibration blob scorer.py reads."""
    clf = LogisticRegression(C=C, max_iter=2000, class_weight="balanced", random_state=seed)
    clf.fit(X, y)
    return {
        "features": FEATURES,
        "mask_terms": MASK_TERMS,
        "coef": [float(c) for c in clf.coef_[0]],
        "intercept": float(clf.intercept_[0]),
        "model_version": f"logit-{time.strftime('%Y%m%d-%H%M%S')}",
        "n_train": int(len(y)),
        "positive_rate": float(np.mean(y)),
    }


def predict(blob: dict, X: np.ndarray) -> np.ndarray:
    z = X @ np.asarray(blob["coef"]) + blob["intercept"]
    return 1.0 / (1.0 + np.exp(-z))


def reliability(probs: np.ndarray, labels: np.ndarray, bins: int = 10) -> list[dict]:
    """10 equal-width bins: [{bin, confidence, accuracy, n}] (empty bins are kept with n = 0)."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(probs, edges[1:-1]), 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        n = int(m.sum())
        out.append(
            {
                "bin": b,
                "confidence": float(probs[m].mean()) if n else float((edges[b] + edges[b + 1]) / 2),
                "accuracy": float(labels[m].mean()) if n else 0.0,
                "n": n,
            }
        )
    return out


def ece(probs: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
    total = len(probs)
    if total == 0:
        return 0.0
    return float(sum(r["n"] / total * abs(r["accuracy"] - r["confidence"]) for r in reliability(probs, labels, bins) if r["n"]))


def save(blob: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=2))
