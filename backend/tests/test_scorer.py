import copy
import itertools

import numpy as np
import pytest

from app.ml.matching import calibrate, features as F, scorer
from tests.helpers import T0, unit, view


def make(**over):
    """A found item that matches the lost one on everything, then overridden."""
    lost = view(kind="lost", category="laptop", category_conf=0.95, colors=["black"], brand="Dell", marks=["dent"], image_embs=[unit(1)], text_emb=unit(2, 384))
    kw = dict(category="laptop", category_conf=0.95, colors=["black"], brand="Dell", marks=["dent"], image_embs=[unit(1)], text_emb=unit(2, 384))
    kw.update(over)
    return lost, view(kind="found", **kw)


def test_weights_sum_to_one():
    assert sum(scorer.WEIGHTS.values()) == pytest.approx(1.0)


def test_perfect_match_scores_high_and_bands():
    lost, found = make()
    r = scorer.score_pair(F.compute_features(lost, found))
    assert r.score > 0.9 and r.band == "strong" and r.coverage == pytest.approx(0.92)  # cross_modal has no text-photo pairing


def test_shares_sum_to_score():
    lost, found = make(colors=["navy"], image_embs=[unit(9)])
    r = scorer.score_pair(F.compute_features(lost, found))
    assert sum(c["contribution"] for c in r.contributions) == pytest.approx(r.score, abs=2e-3)


def test_coverage_discounts_score():
    full_l, full_f = make()
    thin_l = view(kind="lost", category="laptop", category_conf=0.95)
    thin_f = view(kind="found", category="laptop", category_conf=0.95)
    thin = scorer.score_pair(F.compute_features(thin_l, thin_f))
    full = scorer.score_pair(F.compute_features(full_l, full_f))
    assert thin.coverage < full.coverage and thin.score < full.score
    assert thin.raw == pytest.approx(1.0, abs=0.35)  # the raw agreement is high; less evidence lowers the score


def test_masked_features_report_not_compared_and_no_contribution():
    lost = view(kind="lost", category="laptop")
    found = view(kind="found", category="laptop")
    r = scorer.score_pair(F.compute_features(lost, found))
    img = next(c for c in r.contributions if c["key"] == "image")
    assert img["state"] == "not_compared" and img["contribution"] == 0.0 and "Not compared (no photo)" == img["detail"]


def test_states_by_value():
    lost, found = make(colors=["yellow"])
    r = scorer.score_pair(F.compute_features(lost, found))
    color_c = next(c for c in r.contributions if c["key"] == "color")
    assert color_c["state"] == "mismatch"
    assert next(c for c in r.contributions if c["key"] == "brand")["state"] == "match"


def test_monotonic_in_every_feature():
    """Raising any one feature value never lowers the score."""
    base = [F.Feature(k, 0.4, True, "") for k in F.FEATURES]
    for i, key in enumerate(F.FEATURES):
        prev = -1.0
        for v in (0.0, 0.25, 0.5, 0.75, 1.0):
            feats = copy.deepcopy(base)
            feats[i].value = v
            s = scorer.score_pair(feats, calibration=None).score
            assert s >= prev - 1e-9, key
            prev = s


def test_band_thresholds():
    assert scorer.band_for(0.75) == "strong" and scorer.band_for(0.7499) == "possible"
    assert scorer.band_for(0.40) == "possible" and scorer.band_for(0.3999) == "long_shot"


def test_calibrated_scoring_and_shares(tmp_path):
    rng = np.random.default_rng(0)
    X = rng.random((300, len(F.FEATURES) + len(scorer.MASK_TERMS)))
    y = (X[:, :9] @ np.array([2.0, 1, 1, 2, 1, 1, .5, 1, .5]) + rng.normal(0, .5, 300) > 5.5).astype(int)
    blob = calibrate.fit(X, y)
    assert set(blob) >= {"coef", "intercept", "model_version", "features"}
    lost, found = make()
    r = scorer.score_pair(F.compute_features(lost, found), calibration=blob)
    assert 0.0 <= r.score <= 1.0 and r.model_version == blob["model_version"]
    assert sum(c["contribution"] for c in r.contributions) == pytest.approx(r.score, abs=2e-3)


def test_ece_and_reliability():
    probs = np.array([0.1] * 50 + [0.9] * 50)
    perfect = np.array([0] * 45 + [1] * 5 + [0] * 5 + [1] * 45)
    assert calibrate.ece(probs, perfect) == pytest.approx(0.0, abs=1e-9)
    overconfident = np.array([1] * 50 + [0] * 50)
    assert calibrate.ece(probs, overconfident) > 0.5
    rel = calibrate.reliability(probs, perfect)
    assert len(rel) == 10 and sum(r["n"] for r in rel) == 100
